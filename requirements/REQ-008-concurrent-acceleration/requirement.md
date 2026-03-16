# REQ-008 Generic Concurrent Acceleration Framework

> Status: Completed
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Background

12 人狼人杀一局中，每人每次行动需要 3 次串行 LLM 调用（thinker→evaluator→optimizer）。一轮发言+投票 = 12×3×2 = 72 次串行调用，速度极慢。谁是卧底同理。

当前 Runner 的游戏循环通过 `get_current_player()` 每次只获取一个玩家，完全串行。但很多阶段（如投票）玩家之间互不依赖，完全可以并行执行 LLM 调用。

需要一个通用的并发框架：
- Engine 层面声明"哪些玩家可以同时行动"
- Runner 层面通用处理并发执行
- 通过配置控制并发上限，防止 API 限流
- 所有游戏通用受益，不针对特定游戏打补丁

## 2. Target Users & Scenarios

- **开发者：** 通过 `max_concurrency` 配置控制并发强度，平衡游戏速度与 API 限制

## 3. Functional Requirements

### F-01 Engine 声明可并行玩家

- **主流程：**
  - GameEngine 基类新增 `get_actionable_players() -> list[str]`
  - 返回当前所有可以同时行动的玩家列表
  - 默认实现：包装 `get_current_player()`，返回单元素列表（`[pid]` 或 `[]`）
  - 返回多人 = 声明这些人可以并行 think
  - 返回单人 = 串行执行（与当前行为一致）
  - 返回空列表 = 无人可行动（阶段结束）
- **SpyGame 覆写：**
  - 发言阶段：返回 `[当前发言者]`（1人，串行）
  - 投票阶段：返回所有未投票的存活玩家（多人，并行）
- **WerewolfGame 覆写：**
  - 夜晚各角色行动：返回 `[当前角色]`（1人，串行）
  - 白天讨论：返回 `[当前发言者]`（1人，串行）
  - 白天投票：返回所有未投票的存活玩家（多人，并行）
- **边界：** 不改变 `get_current_player()` 的行为，保留向后兼容

### F-02 Runner 通用并发执行

- **主流程：**
  - Runner 游戏循环从调用 `get_current_player()` 改为调用 `get_actionable_players()`
  - 根据返回列表长度决定执行模式：
    - `len == 0`：阶段结束，处理 round end
    - `len == 1`：串行执行（think → apply → record → broadcast）
    - `len > 1`：并行 think，串行 apply
  - 并行模式具体流程：
    1. 所有玩家并行调用 `agent.think_and_act()`（LLM 调用，受 Semaphore 控制）
    2. 收集所有 AgentResponse
    3. 依次串行调用 `engine.apply_action()`（状态修改，保证安全）
    4. 依次记录事件、广播信息
  - 使用 `asyncio.Semaphore(max_concurrency)` 控制同时进行的 LLM 调用数量
- **错误处理：**
  - 并行 think 中某个 agent 失败：使用 fallback response，不影响其他 agent
  - apply_action 失败：记录错误，跳过该玩家，继续处理剩余
- **边界：**
  - `max_concurrency=1` 时行为与当前串行完全一致
  - 不修改 Agent 框架内部（LangGraph 层）

### F-03 并发配置

- **主流程：**
  - `config/app_config.yaml` 新增 `max_concurrency: 1`（默认串行，安全）
  - `AppSettings` 解析该字段，传递给 Runner
  - Runner 用该值初始化 Semaphore
- **边界：** 最小值 1，无上限（用户自行控制风险）

## 4. Non-functional Requirements

- **NF-01 向后兼容：** 默认 `max_concurrency=1`，行为与改动前完全一致
- **NF-02 状态安全：** 并发 think 期间 engine 状态不被修改；apply_action 严格串行
- **NF-03 现有测试通过：** 所有 Spy/Werewolf 测试在 max_concurrency=1 下通过

## 5. Out of Scope

- 发言阶段并行化（玩家需要听前面人的发言，有时序依赖）
- 狼人讨论并行化（轮流交流有时序依赖）
- API 限流自动重试机制（由 LLM client 层处理）
- Evaluator LLM 打分跳过优化（后续独立需求）

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | SpyGame 投票阶段调 `get_actionable_players()` | 返回所有未投票存活玩家 |
| AC-02 | F-01 | SpyGame 发言阶段调 `get_actionable_players()` | 返回单人（当前发言者） |
| AC-03 | F-01 | WerewolfGame 投票阶段 | 返回所有未投票存活玩家 |
| AC-04 | F-01 | WerewolfGame 夜晚守卫阶段 | 返回单人（守卫） |
| AC-05 | F-01 | 基类默认实现 | 包装 get_current_player()，返回 [pid] 或 [] |
| AC-06 | F-02 | `max_concurrency=1` 运行完整游戏 | 行为与改动前串行完全一致 |
| AC-07 | F-02 | `max_concurrency=3` 运行投票阶段 | 最多 3 个 agent 同时调 LLM，结果正确 |
| AC-08 | F-02 | 并发 think 中某 agent 异常 | 使用 fallback，其他 agent 不受影响 |
| AC-09 | F-03 | app_config.yaml 含 max_concurrency=3 | AppSettings 正确解析为 3 |
| AC-10 | NF-03 | 运行所有现有测试（max_concurrency=1） | 全部通过 |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
