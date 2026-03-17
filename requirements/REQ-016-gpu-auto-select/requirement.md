# REQ-016: GPU Auto-Select for Video Rendering

## 1. Background & Motivation

当前 `scripts/render-video.mjs` 的 Remotion 渲染流程存在 GPU 选择缺陷：

- **Chromium ANGLE 渲染**：已配置 `chromiumOptions: { gl: "angle" }`，但 ANGLE 的 D3D11 后端依赖 Windows 图形首选项，默认选择"节能"GPU（即核显）。用户在任务管理器中观察到 AMD 核显（iGPU）打满，而 NVIDIA GTX 4060 空闲。
- **NVENC 编码**：`detectGpuEncoding()` 已实现后处理重编码检测（h264_nvenc / h264_amf / h264_qsv），但 Chromium 页面渲染本身仍跑在核显上，构成瓶颈。
- **跨设备适配缺失**：无论用户有什么 GPU 配置（纯核显、单独显、多 GPU 混合），脚本没有智能选择逻辑，完全依赖系统默认行为。

**核心问题**：Remotion 的 `chromiumOptions` API 不暴露自定义 Chromium 启动参数，无法通过官方接口指定 GPU。需要在脚本层面实现自动检测与智能选择。

## 2. Goals

1. 自动检测系统所有可用 GPU，按性能优先级选择最优 GPU 用于 Chromium 页面渲染
2. 自动选择最优硬件编码器用于视频编码（NVENC > AMF > QSV > CPU x264）
3. 任何设备零配置即用（无需手动设置 Windows 图形首选项或 NVIDIA 控制面板）
4. 启动时打印 GPU 检测报告，让用户清楚知道用了哪个 GPU

## 3. Non-Goals

- 不改变 Remotion 版本或核心渲染架构
- 不修改前端交互式播放（`npm run dev`）的 GPU 行为——那由浏览器自行管理
- 不处理 Linux / macOS 平台（当前项目仅在 Windows 上渲染视频）
- 不在运行时动态切换 GPU（启动时选定，全程使用）

## 4. Functional Requirements

### FR-1: GPU 检测模块

新增 GPU 检测逻辑（在 `render-video.mjs` 内或独立模块），功能：

- **枚举系统 GPU**：通过 `nvidia-smi`、WMIC/PowerShell、或 D3D 信息获取所有 GPU 设备列表
- **分类 GPU 类型**：识别独立显卡（discrete）vs 集成显卡（integrated）
- **识别厂商**：NVIDIA (vendor 0x10DE)、AMD (0x1002)、Intel (0x8086)

输出数据结构示例：
```javascript
{
  gpus: [
    { name: "NVIDIA GeForce RTX 4060 Laptop GPU", vendor: "nvidia", type: "discrete", vendorId: "0x10de" },
    { name: "AMD Radeon(TM) Graphics", vendor: "amd", type: "integrated", vendorId: "0x1002" }
  ],
  selected: { ... },  // 按优先级选中的 GPU
  encoding: { ... }   // 选中的编码器
}
```

### FR-2: GPU 优先级策略

**页面渲染 GPU 选择优先级**（高 → 低）：
1. NVIDIA 独立显卡
2. AMD 独立显卡
3. Intel 独立显卡（如 Arc 系列）
4. AMD / Intel 核显
5. CPU 软件渲染（SwiftShader）——作为最终兜底

**视频编码器选择优先级**（高 → 低）：
1. `h264_nvenc`（NVIDIA NVENC）
2. `h264_amf`（AMD AMF）
3. `h264_qsv`（Intel Quick Sync）
4. `libx264`（CPU 软件编码）——Remotion 默认

### FR-3: Chromium GPU 指定

通过 Monkey-patch Remotion 的浏览器启动逻辑，注入 Chromium 命令行参数来指定 GPU：

- 在 Chromium 启动参数中注入 `--use-angle=d3d11`（确保使用 D3D11 后端）
- 设置 `DXGI_GPU_PREFERENCE=2` 环境变量（告知 D3D 运行时选择高性能 GPU）
- 如果上述方式不生效，考虑注入 `--gpu-testing-vendor-id=0x10de --gpu-testing-device-id=<id>` 直接指定

**Monkey-patch 策略**：
- 拦截 `@remotion/renderer` 的 `internalOpenBrowser` 函数
- 在原始 args 列表中追加 GPU 指定参数
- 确保 patch 安全：如果 Remotion 内部 API 变更，graceful fallback 到默认行为并打印警告

### FR-4: 编码器自动选择（优化现有逻辑）

重构现有 `detectGpuEncoding()`：
- 与 FR-1 的 GPU 检测结果联动——优先使用与页面渲染相同厂商的编码器
- 保留现有的可用性验证（实际编码小片段测试）
- 增加编码器性能信息输出

### FR-5: 启动报告

渲染开始前打印清晰的 GPU 检测报告：

```
========================================
  GPU Detection Report
========================================
  GPUs found:
    [1] NVIDIA GeForce RTX 4060 Laptop GPU (discrete)
    [2] AMD Radeon(TM) Graphics (integrated)

  Page rendering: NVIDIA GeForce RTX 4060 Laptop GPU
  Video encoding: h264_nvenc (NVIDIA NVENC)
========================================
```

如果降级使用了非最优选项，打印警告信息说明原因。

### FR-6: Fallback 与容错

- GPU 检测失败 → 使用 Remotion 默认行为（不 patch），打印警告
- Monkey-patch 失败（Remotion API 变更）→ 跳过 patch，打印警告，继续渲染
- 指定的 GPU 在渲染过程中出错 → 不自动重试（渲染失败即失败，由用户决定）
- 系统无独显 → 正常使用核显，不降级到 SwiftShader

## 5. Technical Constraints

- 实现语言：JavaScript (ESM)，与现有 `render-video.mjs` 一致
- 仅修改 `scripts/render-video.mjs`，不修改 Remotion 源码（node_modules）
- Monkey-patch 必须是运行时 patch，不持久化修改任何文件
- GPU 检测命令超时上限 5 秒，避免阻塞渲染启动
- 兼容 Node.js 18+

## 6. Acceptance Criteria

- [ ] AC-1: 在有 NVIDIA 独显 + AMD 核显的机器上，渲染时任务管理器显示 NVIDIA GPU 使用率上升，核显空闲或低使用率
- [ ] AC-2: 在仅有核显的机器上，正常渲染不报错
- [ ] AC-3: 渲染启动时打印 GPU 检测报告，显示检测到的所有 GPU 和选择结果
- [ ] AC-4: 如果 Monkey-patch 失败，打印警告并继续渲染（不崩溃）
- [ ] AC-5: GPU 编码器自动选择正确（有 NVENC 用 NVENC，无则 fallback）
- [ ] AC-6: 现有渲染功能不受影响——输出视频质量、音画同步等与修改前一致

## Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-17 | Initial version | ALL | - |
