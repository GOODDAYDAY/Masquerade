# REQ-002 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-14
> Updated: 2026-03-14

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Runtime | Python 3.11+ | Same as project |
| Test Runner | Plain script (no pytest) | Per requirement, simple script |
| Async | asyncio | Match existing async flow |
| Mock | Custom MockLLMClient | Replace LLMClient.chat() with queued responses |

## 2. Architecture Overview

测试脚本完全复用现有模块，仅在 LLM 调用层注入 Mock：

```
test_spy_game.py
  └─ GameRunner.run()           # 复用原有 Runner
       ├─ SpyGame (engine)      # 复用原有引擎
       ├─ PlayerAgent            # 复用原有 Agent
       │    ├─ MockLLMClient ← ★ 唯一替换点
       │    └─ LangGraph         # 复用原有图，只是 llm_client 被替换
       └─ GameRecorder           # 复用原有 Recorder
```

### Mock 注入方式

`PlayerAgent.__init__` 内部创建 `LLMClient` 和 `graph`。测试中：

1. 创建 `PlayerAgent` 后，替换 `agent.llm_client` 为 `MockLLMClient`
2. 调用 `build_player_graph(mock_client)` 重建图赋值给 `agent.graph`

这样 Agent 的 `think_and_act()` 以及整个 LangGraph 工作流完全不变，只是底层 LLM 调用走 Mock。

## 3. Module Design

### 3.1 MockLLMClient

```python
class MockLLMClient:
    """Response-queue based mock, interface compatible with LLMClient."""

    def __init__(self, responses: list[str]):
        self._responses = responses
        self._index = 0

    async def chat(self, messages, temperature=0.7) -> str:
        if self._index >= len(self._responses):
            raise RuntimeError("Mock responses exhausted at index %d" % self._index)
        response = self._responses[self._index]
        self._index += 1
        return response
```

- 每个 Agent 持有自己的 MockLLMClient 实例
- 每次 `chat()` 调用消耗一个预编排响应
- 响应耗尽立即抛异常，不会无限循环

### 3.2 LLM 调用计数分析

每个 Agent 决策一次：
- **speak action**: Thinker(1) + Evaluator(1) + Optimizer(1) = **3 calls**
- **vote action**: Thinker(1) + Evaluator(1) + Optimizer(skip) = **2 calls**

场景一（1 轮，4 人）：
- 4 speak × 3 = 12 calls
- 4 vote × 2 = 8 calls
- **每个玩家**：speak(3) + vote(2) = **5 calls**

场景二（2 轮，4 人，第 2 轮 3 人存活）：
- Round 1: 4 speak(12) + 4 vote(8) = 20
- Round 2: 3 speak(9) + 3 vote(6) = 15
- **player_2(spy)**: speak×2(6) + vote×2(4) = **10 calls**
- **player_3**: speak×2(6) + vote×2(4) = **10 calls**
- **player_1**: speak×2(6) + vote×1(2) + vote×1(2) = **10 calls**（第 2 轮被淘汰，但投完票才淘汰）

Wait — player_1 在第 2 轮投完票后被淘汰。player_4 在第 1 轮投完票后被淘汰。

实际每个玩家的 call 数量：
- **player_1**: R1 speak(3)+vote(2) + R2 speak(3)+vote(2) = **10** → 然后被淘汰
- **player_2(spy)**: R1 speak(3)+vote(2) + R2 speak(3)+vote(2) = **10**
- **player_3**: R1 speak(3)+vote(2) + R2 speak(3)+vote(2) = **10**
- **player_4**: R1 speak(3)+vote(2) = **5** → 第 1 轮被淘汰

### 3.3 Mock Response Templates

每个节点期望的 JSON 格式：

**Thinker (speak)**:
```json
{
    "situation_analysis": "分析内容",
    "strategy": "策略内容",
    "action_type": "speak",
    "action_content": "发言内容",
    "expression": "thinking"
}
```

**Thinker (vote)**:
```json
{
    "situation_analysis": "投票分析",
    "strategy": "投票策略",
    "action_type": "vote",
    "action_content": "player_X",
    "expression": "serious"
}
```

**Evaluator (always pass)**:
```json
{
    "score": 8.0,
    "feedback": "Good strategy"
}
```

**Optimizer (speak only)**:
```json
{
    "optimized_content": "润色后的发言",
    "expression": "confident"
}
```

### 3.4 控制随机性

- `random.seed(42)` 固定种子
- SpyGame.setup() 内部用 `random.choice` 和 `random.sample` 分配角色
- 需要验证固定种子下角色分配是否符合预期，不符合则调整种子或直接在 setup 后检查角色分配再构建对应 mock

**更可靠的方案**：setup 后通过 `engine.get_private_info(pid)` 检查每个玩家的角色，动态确定谁是卧底，再据此构建 mock 响应。这样不依赖种子的具体行为。

### 3.5 Test Script Flow

```python
async def run_scenario_civilian_wins():
    """场景一：平民胜"""
    # 1. Setup engine
    engine = SpyGame()
    engine.setup(["p1","p2","p3","p4"], config)

    # 2. Find who is spy
    spy_id = find_spy(engine)

    # 3. Build mock responses per player
    #    - speak: everyone speaks
    #    - vote: everyone votes for spy_id

    # 4. Create agents with mock LLM
    # 5. Get strategy from engine
    # 6. Create recorder
    # 7. Game loop (mirrors GameRunner.run exactly)
    # 8. Verify results
    # 9. Save and verify script JSON

async def run_scenario_spy_wins():
    """场景二：卧底胜"""
    # Similar but 2 rounds, votes target civilians
```

### 3.6 Memory Safety Measures

| Guard | Implementation |
|:---|:---|
| Global timeout | `asyncio.wait_for(scenario(), timeout=15)` per scenario |
| Bounded mock | Response queue, exhaustion = exception |
| Max rounds | `game_config["max_rounds"] = 5` |
| No retry loops | Evaluator mock returns score >= threshold |
| Resource cleanup | No real HTTP client created (MockLLMClient has no connections) |
| Process exit | `sys.exit(0/1)` at end |

## 4. File Structure

```
scripts/
└── test_spy_game.py    # Single self-contained test script
```

No new modules in `backend/`. All mock logic is local to the script.

## 5. Dependencies

仅使用项目现有依赖，无新增。MockLLMClient 是纯 Python，无需任何额外包。
