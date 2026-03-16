# REQ-012 Theater Side Panels — History & Context

> Status: Completed
> Created: 2026-03-16
> Updated: 2026-03-16

## 1. Background

当前 Theater 回放界面主体区域只有一个场景在中央播放，左右两侧完全空白，内容显得"干巴"。用户希望利用左右空间展示历史信息，增强观赏体验和信息密度。

## 2. Target Users & Scenarios

- **前端用户：** 回放时能在侧栏看到之前发生了什么，不用靠记忆追溯

## 3. Functional Requirements

### F-01 右侧面板：发言历史

- 展示所有已播放的 speak / last_words 事件
- 每条记录显示：玩家名（带头像颜色圆点）+ 发言内容摘要（截断过长的）
- 新事件出现时自动滚动到底部
- 可手动向上滚动查看历史
- 分轮次展示，每轮有分隔标记（如"第 1 轮"）

### F-02 左侧面板：行动历史

- 展示所有已播放的非 speak 事件（protect、wolf_discuss、wolf_kill、witch_action、seer_check、vote、hunter_shoot、death_announce 等）
- 每条记录显示：动作图标 + 玩家名 + 简要描述
  - 🛡️ 甄社牛 → 保护甄话多
  - 🐺 甄学霸 → 击杀甄冷静
  - 🔮 甄社牛 → 查验甄阴险
  - 🗳️ 甄暴躁 → 投票甄冷静
  - ☠️ 甄摆烂 死亡
- 同样分轮次、自动滚动、可手动查看

### F-03 响应式布局

- **大屏（≥1280px）：** 左右面板都显示，主体居中
- **中屏（768px~1279px）：** 只显示右侧发言历史面板
- **小屏（<768px）：** 面板全部隐藏，只显示主体
- 面板宽度固定（如 280px），不挤压主体区域
- 面板背景半透明，不遮挡主体边缘

### F-04 视觉风格

- 面板背景：`bg-theater-bg/90` 半透明，与主体自然融合
- 面板内文字小号（text-xs / text-sm），不喧宾夺主
- 当前正在播放的事件在列表中高亮
- 历史条目淡色，当前条目亮色
- 平滑的自动滚动动画

### F-05 数据驱动

- 面板内容从 Theater 上下文获取（timeline 的已播放场景列表）
- 随着场景推进自动追加新条目
- 不依赖具体游戏类型——通过 action.type 和 ACTION_LABELS 通用展示

## 4. Non-functional Requirements

- **NF-01：** 面板渲染不影响主体场景的动画性能
- **NF-02：** 向后兼容，旧版 spy 游戏 JSON 正常展示

## 5. Out of Scope

- 面板内容的搜索/过滤功能
- 点击面板条目跳转到对应场景
- 面板可折叠/拖拽调整大小

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | 播放 speak 事件后 | 右侧面板出现该发言记录 |
| AC-02 | F-01 | 长发言内容 | 截断显示，不撑开面板 |
| AC-03 | F-02 | 播放 wolf_kill 事件后 | 左侧面板出现"🐺 击杀 xxx" |
| AC-04 | F-02 | 播放 vote 事件后 | 左侧面板出现投票记录 |
| AC-05 | F-03 | 窗口 <768px | 面板全部隐藏 |
| AC-06 | F-03 | 窗口 ≥1280px | 两个面板都显示 |
| AC-07 | F-04 | 当前播放事件 | 对应条目高亮 |
| AC-08 | F-05 | spy 游戏 JSON | 面板正常展示（只有 speak 和 vote） |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-16 | Initial version | ALL | - |
