# REQ-002 Spy Game Integration Test Script

> Status: Completed
> Created: 2026-03-14
> Updated: 2026-03-14

## 1. Background

REQ-001 完成了后端骨架，包括 SpyGame 引擎、Agent 框架（LangGraph 工作流）、Orchestrator、Script Recorder 等模块。目前缺少一个端到端集成测试来验证整条链路的完整性。

上一次尝试编写测试脚本时出现了**内存泄漏，导致系统崩溃**。本需求的核心约束是：脚本必须安全可控，严禁无界循环、严禁资源泄漏。

需要一个集成测试脚本，**以与 AI 调用完全相同的方式**驱动游戏——即按照 `GameRunner` → `PlayerAgent.think_and_act()` → LangGraph 工作流 → Engine 状态机 的调用链执行，但用**确定性的 Mock LLM 响应**替代真实 LLM 调用，确保测试可重复、无外部依赖、资源可控。

## 2. Target Users & Scenarios

- **开发者（自己）**：验证 SpyGame 全链路正确性，确保每次改代码后能快速回归
- **CI 环境**：无 LLM API Key 也能运行的自动化验证

## 3. Functional Requirements

### F-01 Mock LLM Client

替换真实 LLM 调用的 Mock 实现。

- Main flow:
  - 创建 `MockLLMClient`，与真实 `LLMClient` 接口一致（`chat()` 方法签名相同）
  - Mock 按预编排的剧本返回确定性响应（JSON 格式，与真实 LLM 输出格式完全一致）
  - 响应内容包含：`situation_analysis`、`strategy`、`action_type`、`action_content`、`expression`（Thinker 节点格式）
  - Evaluator 节点：固定返回高分（`score >= 0.8`），避免触发重试循环
  - Optimizer 节点：原样返回或微调内容
  - 每次调用消耗一个预编排响应，调用次数超出预编排数量时抛出明确异常而非无限循环
- Error handling:
  - 预编排响应耗尽时抛出 `RuntimeError("Mock responses exhausted")`
  - 不允许任何 fallback 或默认响应机制，防止意外的无限循环
- Edge cases: N/A

### F-02 Scenario: Civilian Wins (Spy Eliminated)

平民胜利场景的完整测试。

- Main flow:
  - 4 名玩家（player_1 ~ player_4），其中 1 名卧底
  - 控制词语分配：固定词对（如"苹果/橘子"），固定卧底为 player_3
  - 第一轮：
    - 发言阶段：4 名玩家按顺序发言（使用预编排内容）
    - 投票阶段：投票集中指向 player_3（卧底），player_3 被淘汰
  - 游戏结束：卧底被淘汰 → 平民胜
  - 验证：
    - `engine.is_ended()` == True
    - `engine.get_result().winner` == "civilian"
    - `engine.get_result().eliminated_order` == ["player_3"]
    - `engine.get_result().total_rounds` == 1
    - Recorder 导出的 `GameScript` 包含完整事件
    - 剧本 JSON 文件成功写入 `scripts/` 目录
- Error handling: N/A
- Edge cases: N/A

### F-03 Scenario: Spy Wins (Survives to Final 2)

卧底胜利场景的完整测试。

- Main flow:
  - 4 名玩家（player_1 ~ player_4），其中 1 名卧底
  - 控制词语分配：固定词对，固定卧底为 player_2
  - 第一轮：
    - 发言阶段：4 名玩家发言
    - 投票阶段：投票指向 player_4（平民），player_4 被淘汰
  - 第二轮：
    - 发言阶段：3 名存活玩家发言
    - 投票阶段：投票指向 player_1（平民），player_1 被淘汰
  - 游戏结束：剩余 2 人（player_2 卧底 + player_3 平民） → 卧底胜
  - 验证：
    - `engine.is_ended()` == True
    - `engine.get_result().winner` == "spy"
    - `engine.get_result().eliminated_order` == ["player_4", "player_1"]
    - `engine.get_result().total_rounds` == 2
    - Recorder 导出的 `GameScript` 包含两轮完整事件
    - 剧本 JSON 文件成功写入 `scripts/` 目录
- Error handling: N/A
- Edge cases: N/A

### F-04 Script Output Verification

验证每局游戏结束后剧本正确输出。

- Main flow:
  - 每局游戏结束后，Recorder 调用 `export()` 生成 `GameScript` 对象
  - 调用 `save()` 将 JSON 写入 `scripts/` 目录
  - 验证 JSON 文件存在且大小 > 0
  - 验证 JSON 可反序列化为 `GameScript` 对象
  - 验证 `GameScript.players` 包含所有玩家信息（id, name, role, word）
  - 验证 `GameScript.rounds` 数量与实际轮次一致
  - 验证 `GameScript.result` 不为 None 且 winner 正确
- Error handling: N/A
- Edge cases: N/A

### F-05 Memory Safety Guards

防止内存泄漏和资源失控。

- Main flow:
  - 脚本设置全局超时（如 30 秒），超时强制退出
  - Mock LLM 的响应数量有限且明确，耗尽即报错
  - 游戏最大轮次限制（`max_rounds` 设为合理值如 5）
  - LangGraph 评估重试次数上限（Mock Evaluator 固定高分，不触发重试）
  - 脚本结束后清理所有资源（关闭 AsyncOpenAI client 等）
  - 测试脚本采用独立函数，每个场景独立运行，不共享状态
- Error handling:
  - 任何阶段超时 → 打印错误信息并退出（exit code != 0）
  - 未预期的异常 → 捕获并打印堆栈，退出
- Edge cases: N/A

### F-06 Execution Entry & Output

脚本的运行方式和输出。

- Main flow:
  - 脚本文件：`scripts/test_spy_game.py`
  - 运行方式：`python scripts/test_spy_game.py`
  - 输出格式：
    - 每个场景开始时打印场景名
    - 每轮游戏关键事件打印（谁发言了、谁投票了、谁被淘汰了）
    - 游戏结束打印胜负结果
    - 验证通过打印 ✓，失败打印 ✗ 及原因
    - 最终汇总：X/Y scenarios passed
    - 剧本 JSON 文件路径
  - 退出码：全部通过 exit(0)，有失败 exit(1)
- Error handling: N/A
- Edge cases: N/A

## 4. Non-functional Requirements

- **安全性**：严禁无界循环，所有循环必须有明确上限
- **可重复性**：固定随机种子（`random.seed()`），每次运行结果一致
- **无外部依赖**：不需要 LLM API Key，不需要网络访问
- **执行速度**：整个脚本应在 5 秒内完成
- **资源安全**：内存使用可控，无泄漏，脚本结束后进程正常退出

## 5. Out of Scope

- ~~pytest 框架集成~~ — 纯脚本即可，下个需求再做正式测试
- ~~多游戏类型测试~~ — 本需求只测 Spy 游戏
- ~~性能测试/压力测试~~ — 不需要
- ~~真实 LLM 调用测试~~ — Mock 即可

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-01 | Mock LLM 返回预编排响应 | 返回格式与真实 LLM 一致，可被 Agent 节点正确解析 |
| AC-02 | F-02 | 运行平民胜场景 | 卧底被淘汰，winner="civilian"，1 轮结束 |
| AC-03 | F-03 | 运行卧底胜场景 | 平民逐个被淘汰，winner="spy"，2 轮结束 |
| AC-04 | F-04 | 每局游戏结束 | scripts/ 下生成有效 JSON 剧本文件 |
| AC-05 | F-05 | 运行全部场景 | 无内存泄漏，5 秒内完成，正常退出 |
| AC-06 | F-06 | 运行 python scripts/test_spy_game.py | 输出验证结果，全通过 exit(0) |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-14 | Initial version | ALL | - |
