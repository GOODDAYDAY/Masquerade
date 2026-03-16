# REQ-008 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Concurrency | asyncio.Semaphore + asyncio.gather | Python 原生异步并发，无额外依赖 |
| Config | Pydantic AppSettings (unchanged) | 新增一个字段即可 |
| Engine/Runner | Python (unchanged) | 仅新增接口方法和调用方式 |

## 2. Design Principles

- **Engine 声明，Runner 执行：** Engine 通过返回值的数量声明并行性，Runner 通用处理
- **Think 并行，Apply 串行：** LLM 调用（慢操作）并行，Engine 状态修改（快操作）串行
- **零配置可用：** 默认 `max_concurrency=1`，行为与改动前完全一致

## 3. Architecture Overview

改动集中在三层：

```
Engine 层：新增 get_actionable_players()，各游戏覆写
Runner 层：游戏循环重构，支持 batch 并发执行
Config 层：新增 max_concurrency 字段
```

改动文件清单：

| 文件 | 改动 |
|:---|:---|
| `backend/engine/base.py` | 新增 `get_actionable_players()` 默认实现 |
| `backend/engine/spy/game.py` | 覆写投票阶段返回多人 |
| `backend/engine/werewolf/game.py` | 覆写投票阶段返回多人 |
| `backend/orchestrator/runner.py` | 游戏循环重构：batch 执行 + 并发 think |
| `backend/core/config.py` | AppSettings 新增 `max_concurrency` |
| `config/app_config.yaml` | 新增 `max_concurrency: 1` |

## 4. Module Design

### 4.1 GameEngine 基类扩展

**文件：** `backend/engine/base.py`

新增方法（非 abstract，带默认实现）：

```python
def get_actionable_players(self) -> list[str]:
    """Return all players who can act right now.

    If multiple players are returned, the runner may process their
    LLM thinking in parallel (with concurrency control).
    Default: wraps get_current_player() into a single-element list.
    """
    current = self.get_current_player()
    return [current] if current else []
```

各游戏按需覆写，只在确定无依赖的阶段返回多人。

### 4.2 SpyGame 覆写

**文件：** `backend/engine/spy/game.py`

```python
def get_actionable_players(self) -> list[str]:
    if self.phase == GamePhase.VOTING:
        # All unvoted alive players can think in parallel
        return [pid for pid in self.player_order
                if self.players[pid].alive and pid not in self.votes]
    # Speaking: serial (each player hears previous speeches)
    current = self.get_current_player()
    return [current] if current else []
```

### 4.3 WerewolfGame 覆写

**文件：** `backend/engine/werewolf/game.py`

```python
def get_actionable_players(self) -> list[str]:
    if self.phase == WerewolfPhase.DAY_VOTING:
        return [pid for pid in self.player_order
                if self.players[pid].alive and pid not in self.votes]
    # All other phases: serial (night roles, discussion, last words, etc.)
    current = self.get_current_player()
    return [current] if current else []
```

### 4.4 AppSettings 扩展

**文件：** `backend/core/config.py`

```python
class AppSettings(BaseSettings):
    # ... existing fields ...
    max_concurrency: int = 1  # NEW: max parallel LLM calls (1 = serial)
```

**文件：** `config/app_config.yaml`

```yaml
# Concurrency control: max parallel LLM calls during batch phases (e.g. voting)
# Set to 1 for serial execution (safe default), increase for speed (e.g. 3-5)
max_concurrency: 1
```

### 4.5 GameRunner 重构

**文件：** `backend/orchestrator/runner.py`

#### 4.5.1 核心重构：拆分 think 和 apply

当前 `_agent_turn()` 同时做 think + apply。需要拆分为：

```python
async def _agent_think(self, engine, agent, player_id, strategy) -> AgentResponse:
    """Execute LLM thinking only — no engine state mutation."""
    public_state = engine.get_public_state()
    private_info = engine.get_private_info(player_id)
    available_actions = engine.get_available_actions(player_id)
    rules_prompt = engine.get_game_rules_prompt()
    tools_schema = engine.get_tools_schema()

    return await agent.think_and_act(
        game_rules_prompt=rules_prompt,
        public_state=public_state,
        private_info=private_info,
        available_actions=available_actions,
        tools_schema=tools_schema,
        strategy=strategy,
    )
```

保留 `_agent_turn()` 作为串行模式的便捷方法（think + apply）。

#### 4.5.2 新增：批量处理方法

```python
async def _process_batch(
    self, engine, agents, batch, phase, recorder, max_concurrency,
) -> None:
    """Process a batch of players — parallel think, serial apply."""
    if len(batch) == 1:
        # Serial mode: same as before
        pid = batch[0]
        strategy = engine.get_agent_strategy(pid)
        response = await self._agent_think(engine, agents[pid], pid, strategy)
        engine.apply_action(pid, response.action)
        # log, record, broadcast
        return

    # --- Concurrent mode ---
    logger.info("Concurrent batch: %d players, max_concurrency=%d", len(batch), max_concurrency)

    # 1. Snapshot context for all agents BEFORE any action
    #    (all see the same public state — important for fairness)
    contexts = {}
    for pid in batch:
        contexts[pid] = {
            "strategy": engine.get_agent_strategy(pid),
            "public_state": engine.get_public_state(),
            "private_info": engine.get_private_info(pid),
            "available_actions": engine.get_available_actions(pid),
        }

    # 2. Parallel think with semaphore
    sem = asyncio.Semaphore(max_concurrency)

    async def think_with_limit(pid):
        async with sem:
            ctx = contexts[pid]
            try:
                response = await agents[pid].think_and_act(
                    game_rules_prompt=engine.get_game_rules_prompt(),
                    public_state=ctx["public_state"],
                    private_info=ctx["private_info"],
                    available_actions=ctx["available_actions"],
                    tools_schema=engine.get_tools_schema(),
                    strategy=ctx["strategy"],
                )
                return pid, response, None
            except Exception as e:
                logger.exception("Concurrent think failed for %s", pid)
                return pid, None, e

    results = await asyncio.gather(*[think_with_limit(pid) for pid in batch])

    # 3. Serial apply + record + broadcast
    for pid, response, error in results:
        if error or response is None:
            response = agents[pid]._fallback_response(
                contexts[pid]["available_actions"], 0
            )
        engine.apply_action(pid, response.action)
        log_msg = engine.format_action_log(pid, response.action)
        logger.info(log_msg)
        event = self._build_event(pid, response, agents[pid], phase)
        recorder.record_event(event)
        self._broadcast_action(engine, agents, pid, response.action)
```

#### 4.5.3 游戏循环重构

当前的内循环 (`while engine.get_current_player()`) 改为基于 `get_actionable_players()` 的批量循环：

```python
while not engine.is_ended():
    # Round boundary detection
    live_round = engine.get_public_state().get("round_number", current_round)
    if live_round != current_round:
        break

    batch = engine.get_actionable_players()
    if not batch:
        break  # No more actions this round

    phase = engine.get_public_state().get("phase", "")

    await self._process_batch(
        engine, agents, batch, phase, recorder,
        self.app_settings.max_concurrency,
    )
```

**关键变化：** 不再依赖 `get_current_player()` 驱动循环，改为 `get_actionable_players()` 返回空列表时退出。

## 5. Data Model

无新增数据模型。仅 AppSettings 新增一个 int 字段。

## 6. API Design

无新增 API。

## 7. Key Flows

### 7.1 串行模式（batch=1）

```
Runner → engine.get_actionable_players() → [player_A]
Runner → agent_A.think_and_act() (LLM calls)
Runner → engine.apply_action(player_A, action)
Runner → record + broadcast
Runner → engine.get_actionable_players() → [player_B]
... repeat
```

与当前行为完全一致。

### 7.2 并发模式（batch=N, max_concurrency=3）

```
Runner → engine.get_actionable_players() → [p1, p2, p3, p4, p5]

--- Snapshot context for all 5 players ---

--- Parallel think (Semaphore=3) ---
  Slot 1: p1.think_and_act() ─┐
  Slot 2: p2.think_and_act() ─┤ concurrent
  Slot 3: p3.think_and_act() ─┘
  (p4 waits for a slot)
  Slot 1 done → p4.think_and_act() ─┐
  Slot 2 done → p5.think_and_act() ─┘
--- All responses collected ---

--- Serial apply ---
  engine.apply_action(p1, action) → record → broadcast
  engine.apply_action(p2, action) → record → broadcast
  engine.apply_action(p3, action) → record → broadcast
  engine.apply_action(p4, action) → record → broadcast
  engine.apply_action(p5, action) → record → broadcast

Runner → engine.get_actionable_players() → [] (all voted)
→ Round end
```

### 7.3 Context Snapshot 公平性

并发模式下，所有 batch 内的 agent 在 think 之前获取**同一份** public_state 快照。这确保：
- 投票时所有玩家看到的局面一致（没有人因为先 think 而看到别人的投票结果）
- 与真实桌游一致（投票是同时的）

## 8. Shared Modules & Reuse Strategy

| 共享模块 | 使用者 |
|:---|:---|
| `get_actionable_players()` 默认实现 | 所有游戏引擎（无需覆写也能工作） |
| `_process_batch()` | Runner（通用，不感知具体游戏） |
| `asyncio.Semaphore` | Runner（标准库，无额外依赖） |

未来新增游戏只需在 Engine 中覆写 `get_actionable_players()` 即可享受并发加速，Runner 无需任何修改。

## 9. Risks & Notes

| 风险 | 缓解 |
|:---|:---|
| 并发 think 时 engine 状态被读取 | Context snapshot 在 think 前统一获取，think 期间不调 engine |
| apply_action 顺序影响结果 | 投票结算由最后一个 apply 触发，顺序不影响最终结果 |
| API 限流 | max_concurrency 控制并发数，默认 1 = 串行 |
| agent fallback 响应可能无效 | fallback 使用 available_actions[0]，与当前行为一致 |

**关键设计决策：**

1. **拆分 think 和 apply：** `_agent_think()` 只做 LLM 调用，`apply_action` 由调用方控制时机。这是并发安全的基础。
2. **Context snapshot：** 并发 batch 中所有 agent 看到相同的 public_state，确保公平性。
3. **保留 get_current_player()：** 不删除，`get_actionable_players()` 默认实现依赖它。现有测试中直接调用 `get_current_player()` 的代码不受影响。

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
