# REQ-007 Strategy Tip & Speaking Scene UI Polish

> Status: Completed
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Background

当前 AI 玩家的思考过程（`thinking` 字段）是将局势分析、策略、评估反馈三段原始文本粗暴拼接，格式杂乱，不适合前端展示。用户希望有一个简短的"策略概要"，像内心独白一样展示在发言旁边，增强观赏性。

同时，SpeakingScene 顶部头像区域太小太高，视觉效果不佳，需要优化布局。

## 2. Target Users & Scenarios

- **前端用户：** 观看游戏回放时，能在发言气泡旁边看到玩家的一句话策略内心 OS，增加观赏趣味
- **开发者：** 通过结构化的 `strategy_tip` 字段，更方便地展示和调试 AI 决策逻辑

## 3. Functional Requirements

### F-01 后端：策略概要字段

- **AgentResponse 新增字段：** `strategy_tip: str = ""`，一句话策略概要
- **Optimizer 节点改造：**
  - 修改 optimizer prompt，要求 LLM 额外返回 `strategy_tip` 字段
  - `strategy_tip` 要求：一句简短的内心独白，描述当前策略意图（如"先说个中性的词试探""投给发言最含糊的人"）
  - 投票等非 speak 动作也要生成 strategy_tip
- **GameEvent 新增字段：** `strategy_tip: str = ""`
- **Runner 适配：** 构建 GameEvent 时将 AgentResponse 的 strategy_tip 写入
- **边界：** 不影响现有 thinking 字段的生成逻辑，strategy_tip 是独立的新字段

### F-02 前端：策略内心 OS 展示

- **TypeScript 类型：** `GameEvent` 接口新增 `strategy_tip: string` 字段
- **SpeakingScene 展示：**
  - 在发言气泡上方或旁边增加一个"内心 OS"气泡
  - 使用打字机效果（AnimatedText）展示 strategy_tip 内容
  - 不生成 TTS 音频，纯文字展示
  - 视觉风格与发言气泡区分：斜体、半透明背景、不同颜色调，营造内心独白感
  - strategy_tip 为空时不显示该模块
- **时序：** strategy_tip 打字完成后再开始展示发言气泡（先内心 OS → 再说话），或同时展示均可（优先选择视觉效果更好的方案）

### F-03 SpeakingScene 头像布局优化

- **头像尺寸增大：** 活跃玩家 64px → 保持或增大，其余玩家 40px → 52px
- **间距优化：** 减少头像区与发言区之间的间距（`mb-6` → `mb-3` 或更紧凑）
- **整体效果：** 头像区更紧凑，视觉比例更协调

## 4. Non-functional Requirements

- **NF-01 向后兼容：** `strategy_tip` 字段默认空字符串，旧版脚本 JSON 无此字段时前端不报错
- **NF-02 性能：** Optimizer 新增 strategy_tip 输出不增加额外 LLM 调用（在同一次调用中返回）
- **NF-03 不影响现有测试：** 现有 Spy/Werewolf 测试全部通过

## 5. Out of Scope

- 思考过程（thinking）的完整结构化展示
- VotingScene 中的策略展示
- strategy_tip 的 TTS 音频生成

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | AgentResponse 包含 strategy_tip 字段 | 字段存在且为字符串 |
| AC-02 | F-01 | Optimizer 返回中包含 strategy_tip | speak 和 vote 动作均有 |
| AC-03 | F-01 | 生成的 GameScript JSON | 每个 event 包含 strategy_tip 字段 |
| AC-04 | F-02 | SpeakingScene 有 strategy_tip 时 | 展示内心 OS 气泡，打字机效果 |
| AC-05 | F-02 | SpeakingScene 无 strategy_tip 时 | 不展示内心 OS 模块 |
| AC-06 | F-02 | 内心 OS 气泡样式 | 与发言气泡视觉区分（斜体/半透明等） |
| AC-07 | F-03 | 头像尺寸 | 非活跃玩家 ≥ 52px |
| AC-08 | F-03 | 头像区间距 | 与发言区间距 ≤ 12px（mb-3） |
| AC-09 | NF-01 | 加载旧版无 strategy_tip 的 JSON | 前端正常渲染，不报错 |
| AC-10 | NF-03 | 运行现有测试 | 全部通过 |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
