# REQ-007 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Agent Pipeline | Python / LangGraph (unchanged) | 仅修改 optimizer 节点输出 |
| Script Schema | Pydantic (unchanged) | 新增字段，默认空字符串 |
| Frontend | React / TypeScript / Tailwind (unchanged) | 新增 UI 组件 |

## 2. Design Principles

- **最小改动：** 在现有 optimizer 调用中增加一个返回字段，不新增 LLM 调用
- **向后兼容：** 所有新字段都有默认值，旧 JSON 文件可正常加载
- **关注点分离：** 后端只负责生成 strategy_tip 数据，前端负责展示逻辑

## 3. Architecture Overview

改动链路：

```
Optimizer Node (多返回一个 strategy_tip)
    → AgentState (新增 strategy_tip 字段)
    → PlayerAgent.think_and_act() (提取到 AgentResponse)
    → AgentResponse (新增 strategy_tip 字段)
    → GameRunner._build_event() (写入 GameEvent)
    → GameEvent / schema.py (新增 strategy_tip 字段)
    → JSON 文件
    → Frontend GameEvent TS 类型 (新增 strategy_tip)
    → SpeakingScene (展示内心 OS 气泡)
```

改动文件清单：

| 文件 | 改动 |
|:---|:---|
| `backend/agent/state.py` | AgentState 新增 `strategy_tip: str` |
| `backend/agent/models.py` | AgentResponse 新增 `strategy_tip: str = ""` |
| `backend/agent/nodes/optimizer.py` | 返回中增加 `strategy_tip`，修改 prompt 要求 |
| `backend/agent/player.py` | 提取 `strategy_tip` 写入 AgentResponse |
| `backend/script/schema.py` | GameEvent 新增 `strategy_tip: str = ""` |
| `backend/orchestrator/runner.py` | `_build_event()` 传入 strategy_tip |
| `backend/engine/spy/strategy.py` | optimizer prompt 增加 strategy_tip 要求 |
| `backend/engine/werewolf/strategy.py` | optimizer prompt 增加 strategy_tip 要求 |
| `frontend/src/types/game-script.ts` | GameEvent 接口新增 `strategy_tip` |
| `frontend/src/components/scenes/SpeakingScene.tsx` | 新增内心 OS 气泡 + 头像布局优化 |

## 4. Module Design

### 4.1 Optimizer Node 改造

**文件：** `backend/agent/nodes/optimizer.py`

**当前返回格式：** `{"optimized_content": "...", "expression": "..."}`

**修改后返回格式：** `{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}`

**改动：**
1. 解析 LLM 返回时额外提取 `strategy_tip` 字段
2. 返回 dict 中包含 `strategy_tip`
3. 对 vote 动作（当前跳过 LLM 调用）：从 state 中的 `strategy` 字段截取一句话作为 fallback

**不改变的：** 函数签名、调用方式、与 graph 的集成方式

### 4.2 AgentState 扩展

**文件：** `backend/agent/state.py`

在 Optimizer output 区域新增：

```python
# --- Optimizer output ---
optimized_content: str
expression: str
strategy_tip: str      # NEW
```

### 4.3 AgentResponse 扩展

**文件：** `backend/agent/models.py`

```python
class AgentResponse(BaseModel):
    thinking: str
    action: Action
    expression: str = "neutral"
    thinking_duration_ms: int = 0
    strategy_tip: str = ""    # NEW
```

### 4.4 PlayerAgent 提取

**文件：** `backend/agent/player.py`

在 `think_and_act()` 中，从 graph result 提取 `strategy_tip`：

```python
strategy_tip = result.get("strategy_tip", "")
# ... 构建 AgentResponse 时传入
return AgentResponse(
    thinking=full_thinking,
    action=action,
    expression=...,
    thinking_duration_ms=...,
    strategy_tip=strategy_tip,
)
```

Fallback 响应中 `strategy_tip` 默认空字符串（AgentResponse 的默认值）。

### 4.5 GameEvent 扩展

**文件：** `backend/script/schema.py`

```python
class GameEvent(BaseModel):
    player_id: str
    phase: str
    timestamp: datetime = ...
    thinking_duration_ms: int = 0
    thinking: str = ""
    expression: str = "neutral"
    action: Action
    memory_snapshot: MemorySnapshot = ...
    strategy_tip: str = ""    # NEW — default empty for backward compat
```

### 4.6 Runner 适配

**文件：** `backend/orchestrator/runner.py`

修改 `_build_event()` 方法，增加 `strategy_tip` 参数：

```python
def _build_event(self, player_id, response, agent, phase) -> GameEvent:
    return GameEvent(
        ...,
        strategy_tip=response.strategy_tip,  # NEW
    )
```

### 4.7 Strategy Prompts 修改

**文件：** `backend/engine/spy/strategy.py` 和 `backend/engine/werewolf/strategy.py`

所有 optimizer prompt 的返回格式要求从：

```
返回 JSON 格式：{"optimized_content": "...", "expression": "..."}
```

改为：

```
返回 JSON 格式：{"optimized_content": "...", "expression": "...", "strategy_tip": "..."}

strategy_tip 要求：一句简短的内心独白，描述你当前的策略意图。例如："先说个中性的描述试探一下""他的发言太含糊了，投他"
```

### 4.8 前端 TypeScript 类型

**文件：** `frontend/src/types/game-script.ts`

```typescript
export interface GameEvent {
  // ... existing fields ...
  strategy_tip?: string;  // optional for backward compat
}
```

使用 `?` 可选字段确保旧 JSON 不报错。

### 4.9 SpeakingScene UI 改造

**文件：** `frontend/src/components/scenes/SpeakingScene.tsx`

#### 布局结构（改造后）

```
<div className="h-full flex flex-col px-6 py-4">
  {/* Avatar Row — 尺寸增大，间距收紧 */}
  <div className="flex gap-3 justify-center mb-3 flex-wrap">
    <PlayerAvatar size={isActive ? 64 : 52} ... />
  </div>

  {/* Speech Content — 居中 */}
  <div className="flex-1 flex flex-col items-center justify-center min-h-0">
    {/* Speaker header */}
    <div>name + expression + round</div>

    {/* Strategy Tip — 内心 OS 气泡（仅有内容时展示） */}
    {strategyTip && (
      <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-2 max-w-md w-full mb-3">
        <span className="text-xs text-gray-500 mr-1">💭</span>
        <AnimatedText text={strategyTip}
          className="text-sm text-gray-400 italic leading-relaxed inline" />
      </div>
    )}

    {/* Speech Bubble — 发言气泡 */}
    <div className="bg-theater-surface border ...">
      <AnimatedText text={speechContent} ... />
    </div>
  </div>
</div>
```

#### 内心 OS 气泡视觉设计

| 属性 | 发言气泡 | 内心 OS 气泡 |
|:---|:---|:---|
| 背景 | `bg-theater-surface` (#14141f) | `bg-white/5` (微透明白) |
| 边框 | `border-theater-border` | `border-white/10` |
| 文字颜色 | `text-gray-200` | `text-gray-400` (更淡) |
| 字体 | 正常 | `italic` 斜体 |
| 字号 | `text-base` | `text-sm` (稍小) |
| 圆角 | `rounded-2xl` | `rounded-xl` |
| 前缀 | 无 | 💭 emoji |
| 最大宽度 | `max-w-xl` | `max-w-md` (更窄) |

#### 时序处理

- strategy_tip 和 speech 同时展示，共用同一个场景时长
- 场景时长计算仍以 speech 的文本长度 + 音频长度为准（strategy_tip 不参与时长计算）
- strategy_tip 打字速度使用相同的 `TEXT_SPEED`

## 5. Data Model

新增字段一览（全部默认空字符串，向后兼容）：

| 层 | 类/接口 | 新字段 | 默认值 |
|:---|:---|:---|:---|
| Agent State | `AgentState` | `strategy_tip: str` | (TypedDict, optional) |
| Agent Response | `AgentResponse` | `strategy_tip: str` | `""` |
| Script Schema | `GameEvent` | `strategy_tip: str` | `""` |
| Frontend Type | `GameEvent` | `strategy_tip?: string` | `undefined` |

## 6. API Design

无新增 API。数据通过 JSON 文件传递。

## 7. Key Flows

### 7.1 Strategy Tip 生成流程

```
Thinker → strategy (raw)
  ↓
Evaluator → pass/retry
  ↓
Optimizer → LLM call with updated prompt
  ↓ parse JSON
  ↓ extract optimized_content, expression, strategy_tip
  ↓
AgentState.strategy_tip = parsed value
  ↓
PlayerAgent → AgentResponse.strategy_tip
  ↓
Runner._build_event() → GameEvent.strategy_tip
  ↓
Recorder → JSON file
  ↓
Frontend → SpeakingScene renders tip bubble
```

### 7.2 Vote 动作的 Strategy Tip

Optimizer 当前跳过 vote 动作的 LLM 调用。为 vote 生成 strategy_tip 的方案：

从 state 中的 `strategy` 字段提取。`strategy` 是 thinker 生成的策略文本，截取前 50 个字符作为 tip。如果为空则使用默认文案。

## 8. Shared Modules & Reuse Strategy

| 共享模块 | 使用者 |
|:---|:---|
| `AnimatedText` 组件 | SpeakingScene（speech + strategy_tip 两处使用） |
| `AgentState` TypedDict | 所有 agent 节点 |
| `GameEvent` schema | Runner + Recorder + Frontend |

## 9. Risks & Notes

| 风险 | 缓解 |
|:---|:---|
| LLM 不返回 strategy_tip 字段 | Optimizer 中 fallback 为空字符串，前端判空不展示 |
| 旧 JSON 无 strategy_tip | Pydantic 默认值 + TS optional 字段 |
| 所有游戏 strategy prompt 需同步修改 | Spy(3套) + Werewolf(10套) 的 optimizer prompt 均需添加 strategy_tip 要求 |

**关键决策：** strategy_tip 和 speech 同时展示（而非先后），理由是：先后展示会增加场景时长、实现复杂度高，且同时展示更像"边想边说"的真实感。

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
