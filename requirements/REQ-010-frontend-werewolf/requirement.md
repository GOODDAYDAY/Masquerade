# REQ-010 Frontend Game-Agnostic Refactor

> Status: Completed
> Created: 2026-03-16
> Updated: 2026-03-16

## 1. Background

前端 Theater 回放系统完全为谁是卧底设计，狼人杀游戏的回放存在严重问题：

- 夜晚阶段（守卫/狼人讨论/女巫/预言家）完全不可见 — timeline.ts 只取 speak/vote
- Header 显示"平民词/卧底词" — 狼人杀没有词概念
- 胜负文本不识别 "wolf"/"village" winner
- OpeningScene 显示 word 字段 — 狼人杀用角色/阵营
- 没有夜晚场景组件

需要将前端重构为**游戏无关**架构，类似后端的 Engine/Runner 分离：JSON 数据驱动渲染，组件不硬编码具体游戏逻辑。

## 2. Target Users & Scenarios

- **前端用户：** 能正确回放狼人杀和谁是卧底的完整游戏过程，包括夜晚阶段

## 3. Functional Requirements

### F-01 Timeline 支持所有动作类型

- **当前问题：** timeline.ts 只过滤 `action.type === "speak"` 和 `"vote"`，其他全部丢弃
- **修复：** timeline 从 round.events 中构建场景时，按 action.type 分类：
  - `speak` / `last_words` → SpeakingScene（已有）
  - `vote` → VotingScene（已有）
  - 其他（`wolf_discuss` / `protect` / `wolf_kill` / `witch_action` / `seer_check` / `hunter_shoot`）→ ActionScene（新增）
- **通用原则：** 不硬编码动作类型列表，而是：已知类型用对应组件，未知类型用 ActionScene 兜底
- **场景顺序：** 按 event 在 round.events 中的原始顺序排列，不再按类型分组

### F-02 ActionScene — 通用动作场景组件

- **新增组件：** 用于展示非 speak/vote 的所有动作（夜晚行动、遗言、猎人开枪等）
- **展示内容：**
  - 玩家名 + 动作类型标签（如"守卫保护""狼人讨论""女巫用药""预言家查验"）
  - 动作内容：payload 中的 gesture/target/use 等字段
  - strategy_tip（如果有）
- **视觉风格：**
  - 夜晚 phase（phase 以 `night_` 开头）：暗色背景、月亮图标
  - 白天 phase：正常风格
- **动作类型标签映射：** 组件内维护一个 `actionTypeLabels` map，将 action.type 映射为中文标签
- **通用性：** 未知 action.type 显示原始类型名，不崩溃

### F-03 Theater Header 游戏类型感知

- **当前问题：** 硬编码显示平民词/卧底词
- **修复：** 根据 `script.game.type` 展示不同内容：
  - `spy`：显示平民词 vs 卧底词（保留现有逻辑）
  - `werewolf`：显示角色阵营信息（如"狼人杀 · 12人局"）
  - 其他/未知：显示游戏类型名
- **不硬编码所有游戏类型：** spy 有特殊展示（词对），其余走通用

### F-04 FinaleScene 支持通用 winner

- **当前问题：** 只识别 "civilian"/"spy"/"blank" winner
- **修复：** 增加 winner 映射：
  - `village` → "好人阵营获胜"
  - `wolf` → "狼人阵营获胜"
  - 兜底：未知 winner 显示原始值

### F-05 OpeningScene 适配

- **当前问题：** 显示 word 字段，狼人杀没有 word
- **修复：** 根据玩家数据决定展示：
  - 有 word → 显示 word（spy 游戏）
  - 无 word 但有 role → 显示角色名（werewolf 游戏）
  - 有 extra.faction → 显示阵营标签
- **通用性：** 不检查 game.type，而是根据数据是否存在来决定展示

### F-06 GameEvent 类型泛化

- **当前问题：** `phase: "speaking" | "voting"` 硬编码
- **修复：** 改为 `phase: string`，支持所有游戏的 phase 值

## 4. Non-functional Requirements

- **NF-01 向后兼容：** 旧版 spy 游戏 JSON 回放不受影响
- **NF-02 高内聚低耦合：** 组件不依赖具体游戏类型，通过数据驱动渲染
- **NF-03 未知动作不崩溃：** 未来新增游戏/动作类型时，前端自动兜底展示

## 5. Out of Scope

- 前端新增的夜晚场景的 TTS 音频播放（夜晚动作是手势，不需要 TTS）
- 前端针对具体游戏的定制 UI（如狼人杀专属主题色）
- 后端 JSON 结构变更

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | 加载狼人杀 JSON | 夜晚阶段事件在回放中可见 |
| AC-02 | F-01 | 加载谁是卧底 JSON | 回放行为与改动前一致 |
| AC-03 | F-02 | wolf_discuss 事件 | 显示动作描述 + "狼人讨论"标签 |
| AC-04 | F-02 | seer_check 事件 | 显示"预言家查验"标签 + 目标 |
| AC-05 | F-02 | 未知 action.type | 显示原始类型名，不崩溃 |
| AC-06 | F-03 | 狼人杀 JSON | Header 不显示平民词/卧底词 |
| AC-07 | F-03 | 谁是卧底 JSON | Header 仍显示平民词/卧底词 |
| AC-08 | F-04 | winner="wolf" | 显示"狼人阵营获胜" |
| AC-09 | F-04 | winner="village" | 显示"好人阵营获胜" |
| AC-10 | F-05 | 狼人杀 OpeningScene | 显示角色名 + 阵营，不显示空 word |
| AC-11 | F-06 | TypeScript 编译 | phase: string 无类型错误 |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-16 | Initial version | ALL | - |
