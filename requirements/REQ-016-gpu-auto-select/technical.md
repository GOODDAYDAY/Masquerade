# REQ-016: GPU Auto-Select — Technical Design

## 1. Overview

在 `scripts/render-video.mjs` 中新增 GPU 自动检测与选择逻辑，通过 monkey-patch Remotion 内部的浏览器启动函数，注入 Chromium GPU 指定参数，使 ANGLE 后端优先使用高性能独立显卡。同时重构编码器检测，与 GPU 检测结果联动。

## 2. Architecture

所有改动集中在 `scripts/render-video.mjs` 单文件内。不新增独立模块，不修改 node_modules。

```
render-video.mjs
├── GPU Detection (new)
│   ├── detectSystemGpus()      — 枚举系统 GPU
│   └── selectOptimalGpu()      — 按优先级选择
├── Chromium GPU Patch (new)
│   └── patchRemotionBrowser()  — monkey-patch launchChrome
├── Encoder Detection (refactored)
│   └── detectGpuEncoding()     — 与 GPU 检测联动
├── Bundle (existing)
├── Render (existing)
└── Post-process (existing)
```

## 3. Detailed Design

### 3.1 GPU Detection — `detectSystemGpus()`

**检测策略**：使用 PowerShell 的 `Get-CimInstance Win32_VideoController` 获取所有 GPU 信息，这是 Windows 上最可靠的方法。

```javascript
function detectSystemGpus() {
  // PowerShell query: name, vendorId (PNPDeviceID contains VEN_xxxx), adapterRAM
  const psCommand = `powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID,AdapterRAM,VideoProcessor | ConvertTo-Json"`;
  const output = execSync(psCommand, { encoding: "utf-8", timeout: 5000 });
  const controllers = JSON.parse(output);
  // ... parse and classify
}
```

**分类逻辑**：

| 判定条件 | 分类 |
|:---|:---|
| Vendor ID 包含 `VEN_10DE` | NVIDIA |
| Vendor ID 包含 `VEN_1002` | AMD |
| Vendor ID 包含 `VEN_8086` | Intel |
| 名称包含常见集成关键词 且 显存 ≤ 2GB | integrated |
| 其他 | discrete |

集成显卡判定关键词：`Radeon(TM) Graphics`（无型号后缀）, `UHD Graphics`, `Iris`, `Vega`（嵌入 APU 名称中的）。

**Fallback**：PowerShell 失败时，尝试 `nvidia-smi --query-gpu=name,pci.device_id --format=csv,noheader` 检测 NVIDIA GPU。全部失败返回空列表。

### 3.2 GPU Priority Selection — `selectOptimalGpu()`

```javascript
function selectOptimalGpu(gpus) {
  // Priority: NVIDIA discrete > AMD discrete > Intel discrete > any iGPU > null
  const priority = [
    (g) => g.vendor === "nvidia" && g.type === "discrete",
    (g) => g.vendor === "amd" && g.type === "discrete",
    (g) => g.vendor === "intel" && g.type === "discrete",
    (g) => g.type === "integrated",
  ];
  for (const pred of priority) {
    const match = gpus.find(pred);
    if (match) return match;
  }
  return null;
}
```

返回值包含：`{ name, vendor, type, vendorId, deviceId }`。

### 3.3 Chromium GPU Patch — `patchRemotionBrowser()`

**Patch 目标**：`@remotion/renderer/dist/browser/Launcher.js` 的 `exports.launchChrome`。

**选择 patch `launchChrome` 而非 `internalOpenBrowser` 的原因**：
- `launchChrome` 是最终构造 Chrome 进程参数的地方，直接操作 `args` 数组
- 避免干扰 `internalOpenBrowser` 中的其他逻辑（browser download, path resolution 等）
- `launchChrome` 签名简单：`{ args, executablePath, ... }` → 只需追加 args

**Patch 实现**：

```javascript
function patchRemotionBrowser(selectedGpu) {
  try {
    const launcherPath = require.resolve("@remotion/renderer/dist/browser/Launcher.js");
    const launcherModule = require(launcherPath);
    const originalLaunchChrome = launcherModule.launchChrome;

    launcherModule.launchChrome = async (opts) => {
      const extraArgs = buildGpuArgs(selectedGpu);
      opts.args = [...(opts.args || []), ...extraArgs];
      return originalLaunchChrome(opts);
    };

    return true;
  } catch (e) {
    console.warn(`  [WARN] Browser GPU patch failed: ${e.message}`);
    return false;
  }
}
```

**`buildGpuArgs(gpu)` 生成的 Chromium 参数**：

| 参数 | 作用 | 适用条件 |
|:---|:---|:---|
| `--use-angle=d3d11` | 强制 ANGLE 使用 D3D11 后端 | 始终 |
| `--ignore-gpu-blocklist` | 防止 Chrome 黑名单禁用 GPU | 始终（已存在，但确保） |
| `--enable-gpu` | 强制启用 GPU 合成 | 始终 |

**环境变量**（在 patch 前设置）：

| 变量 | 值 | 作用 |
|:---|:---|:---|
| `DXGI_GPU_PREFERENCE` | `2` | Windows DXGI 提示：选择高性能 GPU |
| `SHIM_MCCOMPAT` | `0x800000001` | Windows Hybrid Graphics 提示：选择独显 |

> **关于 `--gpu-testing-vendor-id`**：此参数仅影响 Chrome 内部的 GPU 信息报告（chrome://gpu），不实际控制 DXGI 适配器选择。因此不使用该参数，改用 DXGI 环境变量方案。

### 3.4 Encoder Detection Refactor

重构现有 `detectGpuEncoding()`，与 GPU 检测联动：

```javascript
function detectGpuEncoding(selectedGpu) {
  // Reorder candidates based on selected GPU vendor
  let candidates;
  if (selectedGpu?.vendor === "nvidia") {
    candidates = ["h264_nvenc", "h264_amf", "h264_qsv"];
  } else if (selectedGpu?.vendor === "amd") {
    candidates = ["h264_amf", "h264_nvenc", "h264_qsv"];
  } else if (selectedGpu?.vendor === "intel") {
    candidates = ["h264_qsv", "h264_nvenc", "h264_amf"];
  } else {
    candidates = ["h264_nvenc", "h264_amf", "h264_qsv"];
  }
  // ... rest of detection logic (unchanged)
}
```

### 3.5 Startup Report

在 Bundle 之前，Composition 加载之前输出：

```
========================================
  GPU Detection Report
========================================
  GPUs found:
    [1] NVIDIA GeForce RTX 4060 Laptop GPU (discrete) ← selected
    [2] AMD Radeon(TM) Graphics (integrated)

  Page rendering : NVIDIA GeForce RTX 4060 Laptop GPU (via ANGLE D3D11)
  Browser patch  : applied (launchChrome args injected)
  Video encoding : h264_nvenc (NVIDIA NVENC)
========================================
```

### 3.6 Execution Flow (Modified)

```
1. Parse CLI args                    (existing, unchanged)
2. detectSystemGpus()                ← NEW
3. selectOptimalGpu()                ← NEW
4. patchRemotionBrowser(selectedGpu) ← NEW
5. Set DXGI environment variables    ← NEW
6. Print GPU Detection Report        ← NEW
7. Bundle                            (existing, unchanged)
8. Select Composition                (existing, chromiumOptions unchanged — gl:"angle")
9. detectGpuEncoding(selectedGpu)    ← REFACTORED (vendor-aware ordering)
10. Render                           (existing, unchanged)
11. GPU re-encode (if available)     (existing, unchanged)
```

## 4. Risk Analysis

| Risk | Probability | Impact | Mitigation |
|:---|:---|:---|:---|
| Remotion 升级改变 Launcher.js 导出结构 | 低 | Patch 失败 | try-catch 包裹，fallback 到默认行为，打印警告 |
| DXGI_GPU_PREFERENCE 环境变量在某些 Windows 版本不生效 | 中 | 继续使用核显 | 作为 best-effort，结合 SHIM_MCCOMPAT 双重设置 |
| PowerShell GPU 查询被安全策略阻止 | 低 | 检测失败 | Fallback 到 nvidia-smi，再失败则跳过检测 |
| 多 NVIDIA GPU 的系统选错卡 | 低 | 次优性能 | DXGI_GPU_PREFERENCE=2 让系统选最高性能的 |

## 5. Test Strategy

无需自动化测试（GPU 行为依赖硬件环境）。验证方式：

1. **有 NVIDIA + iGPU 的机器**：运行渲染，观察任务管理器 GPU 使用率
2. **仅有 iGPU 的机器**（如无独显笔记本）：确认正常渲染不报错
3. **检查启动报告**：确认 GPU 列表和选择结果正确

## Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-17 | Initial version | ALL | - |
