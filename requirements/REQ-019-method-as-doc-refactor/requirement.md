# REQ-019: Method as Documentation 编码规范重构

| Field | Value |
|:---|:---|
| ID | REQ-019 |
| Status | Completed |
| Created | 2026-03-20 |
| Type | 代码重构 |

---

## 1. 目标

将现有代码重构为 **"Method as Documentation"** 风格：
- 公开方法只做编排（读起来像业务流程图）
- 每个步骤抽取为语义清晰的私有方法
- 递归适用于每一层

**不改变任何功能行为**，纯重构。

---

## 2. 重构范围

扫描结果：9 个文件需要重构，按优先级分组。

### 2.1 高优先级（核心管线 + 主循环）

| 文件 | 问题 | 改动要点 |
|:---|:---|:---|
| `agent/nodes/thinker.py` | `thinker_node()` 混合了 prompt 构建、JSON 解析、日志 | 拆为 `_build_prompt()`, `_parse_response()`, `_log_result()` |
| `agent/nodes/evaluator.py` | `evaluator_node()` 混合了验证、prompt 构建、解析；`_force_fix_action()` 做太多事 | 拆为 `_run_programmatic_validation()`, `_build_prompt()`, `_parse_response()`；拆 `_fix_action_type()`, `_fix_payload_fields()` |
| `agent/nodes/optimizer.py` | `optimizer_node()` 混合了内容检测、prompt 构建、解析 | 拆为 `_should_optimize()`, `_build_prompt()`, `_parse_response()` |
| `orchestrator/runner.py` | `run()` 140+ 行；`_process_batch()` 逻辑密集 | `run()` 拆为 `_setup_engine()`, `_setup_grg()`, `_create_agents()`, `_setup_recorder()`, `_run_game_loop()`；`_process_batch()` 拆为 `_snapshot_contexts()`, `_think_concurrent()`, `_apply_and_record_results()` |
| `engine/werewolf/game.py` | `get_available_actions()`, `get_current_player()`, `get_tools_schema()`, `get_agent_strategy()` 都有大段 if/elif 分支 | 每个方法拆出 phase/role 维度的辅助方法 |

### 2.2 中优先级

| 文件 | 问题 | 改动要点 |
|:---|:---|:---|
| `agent/player.py` | `think_and_act()` 混合了 state 构建、graph 调用、结果组装 | 拆为 `_build_initial_state()`, `_invoke_graph()`, `_build_response()` |
| `agent/llm_client.py` | `chat()` 内含重试循环 | 拆为 `_chat_with_retries()` |
| `tts/generate.py` | `generate_audio()` 混合了目录创建、事件收集、音频生成 | 拆为 `_setup_audio_dir()`, `_collect_speech_events()`, `_generate_and_build_manifest()` |

### 2.3 低优先级

| 文件 | 问题 | 改动要点 |
|:---|:---|:---|
| `engine/spy/game.py` | `get_tools_schema()` 有 if/elif 链；`_get_eliminated_in_round()` 计票逻辑内联 | 拆出 phase schema 方法和 `_count_votes()` |

### 2.4 不需要改动的文件（已符合规范）

- `agent/graph.py` — 纯编排
- `agent/memory.py`, `agent/models.py`, `agent/strategy.py`, `agent/state.py` — 数据模型
- `core/config.py`, `core/exceptions.py`, `core/logging.py` — 基础设施
- `engine/base.py`, `engine/models.py`, `engine/registry.py` — 接口/模型
- `engine/shared_prompts.py`, `engine/spy/prompts.py`, `engine/spy/strategy.py`, `engine/spy/words.py` — 常量/工厂
- `engine/werewolf/prompts.py`, `engine/werewolf/strategy.py` — 常量/工厂
- `orchestrator/event_bus.py` — 干净的观察者模式
- `script/recorder.py`, `script/schema.py` — 已符合
- `tts/voices.py` — 纯函数
- `main.py` — CLI 入口
- `reasoning/*` — 刚写的，已符合

---

## 3. 重构原则

1. **纯重构，不改行为** — 不新增功能，不修改逻辑，只改结构
2. **公开方法 = 编排** — 方法体只有私有方法调用和简单变量传递
3. **私有方法 = 最小业务单元** — 每个做且只做一件事
4. **保持现有测试通过** — 重构后所有测试必须绿色
5. **不过度拆分** — 2-3 行的简单条件不需要抽方法
