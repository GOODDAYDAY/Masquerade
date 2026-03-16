# REQ-011 Technical Design

> Status: Technical Finalized
> Requirement: requirement.md
> Created: 2026-03-16
> Updated: 2026-03-16

## 1. Technology Stack

无新增。纯 prompt 文本修改 + Runner 小改动 + 前端标签。

## 2. Design Principles

- Prompt 修改不改变 agent 框架调用方式
- death_announce 事件通用化，所有游戏可用

## 3. Architecture Overview

| 文件 | Feature | 改动量 |
|:---|:---|:---|
| `backend/engine/werewolf/strategy.py` | F-01~F-07 | 大（重写所有 thinker prompt） |
| `backend/orchestrator/runner.py` | F-08 | 小（夜晚结算后插入事件） |
| `frontend/src/components/scenes/ActionScene.tsx` | F-08 | 1 行（ACTION_LABELS 加条目） |

## 4. Module Design

### 4.1 F-08: Death Announce 事件

**Runner 改动位置：** `_process_serial` 和 `_process_batch` 之后、round-end 处理之前。

实际上更好的位置是：每轮开始时，检查 engine 的 `night_deaths`，如果有死亡就插入事件。

**方案：** 在 Runner 的外层循环中，每轮的内循环结束后，检查 `engine.get_public_state()["night_deaths"]`，如果非空，为每个死者生成一个 death_announce 事件记录到 recorder。

```python
# After inner loop, before round-end processing
public_state = engine.get_public_state()
night_deaths = public_state.get("night_deaths", [])
if night_deaths:
    death_event = GameEvent(
        player_id="system",
        phase="death_announce",
        action=Action(type="death_announce", player_id="system",
                      payload={"deaths": ",".join(night_deaths)}),
    )
    recorder.record_event(death_event)
```

**前端：** ActionScene 的 ACTION_LABELS 加：
```typescript
death_announce: "☠️ 死亡公告",
```

ActionScene 展示 payload.deaths 中的玩家名列表。

### 4.2 F-01~F-07: Prompt 重写策略

所有 thinker prompt 的改动原则：
- **增加分析维度：** 不止"哪个玩家威胁大"，要考虑其他角色的行为模式
- **增加博弈深度：** 引入反向思维、心理博弈
- **减少模式化：** 明确要求"不要每次都用相同模式"
- **保留结构：** JSON 输出格式不变（situation_analysis, strategy, action_type, action_content, expression）

#### 4.2.1 狼人 Night Prompt

新增分析维度：
- 守卫预判（上轮保护了谁？这轮不能连续保护，所以守卫的选择范围有限）
- 女巫状态（第一晚可能有解药，后面可能没有）
- 反预测选目标（"如果守卫保护了显眼的人，我们就刀不显眼的"）
- 讨论引导（第一轮提出候选，第二轮回应+确认，不重复动作）

#### 4.2.2 狼人 Day Prompt

新增策略引导：
- 考虑是否悍跳预言家（分析场上是否已有人跳）
- 如何引导好人互投（不直接暴露狼队关系）
- 利用已知信息差（狼人知道谁是队友，可以判断其他人的身份推理是否正确）

#### 4.2.3 预言家 Prompt

新增策略引导：
- 首验策略（验最可疑的人而非随机）
- 跳身份时机（首轮跳还是等到查到狼再跳？有对跳时如何应对？）
- 查验结果传递（如何让好人信服你的查验，而非被当成悍跳狼）
- 带队投票（查到狼了就要明确归票目标）

#### 4.2.4 女巫 Prompt

核心改动——**毒药使用引导**：
- "如果白天讨论中有玩家被多人质疑且逻辑有漏洞，考虑使用毒药"
- "不要总是 skip！毒药不用等于浪费"
- "如果你有较大把握某人是狼，毒药比等待更有效"
- 解药策略：首夜救不救的分析框架

#### 4.2.5 守卫 Prompt

核心改动——**反向博弈**：
- "分析狼人最可能刀谁——然后保护那个人"
- "但狼人也可能猜到你的想法——考虑二级博弈"
- "如果上轮是平安夜，分析是你守中了还是女巫救了"
- "考虑守自己——如果你暴露了守卫身份"

#### 4.2.6 村民 Prompt

核心改动——**逻辑分析**：
- "分析每个人发言的逻辑链是否自洽"
- "对跳预言家时如何判断谁是真的（看查验逻辑、发言状态、站边情况）"
- "投票时跟大多数好人归票，不要分散票数"
- "关注沉默玩家和最后一个发言的人"

#### 4.2.7 猎人 Prompt

核心改动——**开枪果断**：
- "死亡时如果有合理怀疑，就开枪带走那个人"
- "宁可猜错也不要浪费技能不开枪"
- "白天被投票时可以亮身份保命"

## 5. Data Model

GameEvent 中 `player_id="system"` 用于系统事件（death_announce），不关联具体玩家。

## 6. API Design

无新增。

## 7. Key Flows

无新增流程，仅 prompt 内容升级 + death_announce 事件插入。

## 8. Shared Modules & Reuse Strategy

death_announce 事件通用——所有游戏都可以在夜晚结算后使用（如果 engine 提供 night_deaths）。

## 9. Risks & Notes

| 风险 | 缓解 |
|:---|:---|
| Prompt 太长导致 LLM 忽略部分指令 | 核心指令加粗加星号，放在 prompt 前面 |
| DeepSeek 对复杂策略理解不足 | 用具体案例示范而非抽象描述 |
| death_announce 中 player_id="system" | 前端 ActionScene 需处理找不到 player 的情况 |

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-16 | Initial version | ALL | - |
