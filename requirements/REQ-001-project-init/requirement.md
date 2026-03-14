# REQ-001 Project Init — Backend Skeleton & Core Interfaces

> Status: Completed
> Created: 2026-03-14
> Updated: 2026-03-14

## 1. Background

Masquerade 是一个 AI 桌游对弈平台，让多个 LLM Agent 自动对弈桌游并生成结构化剧本。本需求为项目初始化：搭建后端骨架、定义核心接口与数据模型、实现第一个游戏（谁是卧底），建立高内聚低耦合的模块结构，使后续新游戏可即插即用。

当前阶段聚焦后端，展示层（前端回放 + 视频渲染）后续独立需求处理。

## 2. Target Users & Scenarios

- **开发者（自己）**：基于骨架快速开发新游戏和新功能
- **API 消费者**：通过 HTTP 接口触发游戏、查询剧本

## 3. Functional Requirements

### F-01 Project Structure & Package Init

项目目录结构与 Python 包初始化。

- Main flow:
  - 按模块职责创建目录和 `__init__.py`
  - 后端模块（`backend/` 下）：`engine/`、`agent/`、`orchestrator/`、`script/`、`api/`（可选）、`core/`
  - 预留目录（`backend/` 下）：`renderer/`（视频渲染管线，暂不实现）
  - 项目根目录：`config/`（配置文件）、`scripts/`（剧本输出）、`output/`（视频输出）、`logs/`（日志）、`assets/`（素材）、`models/`（SD模型）、`.env.example`（环境变量示例）
  - 项目配置：`pyproject.toml` 定义依赖与元信息
- Error handling: N/A
- Edge cases: N/A

### F-02 Config Module

统一的配置管理模块。

- Main flow:
  - `core/config.py`：Pydantic Settings，从 YAML + 环境变量 + .env 加载配置
  - `config/app_config.yaml`：应用级配置（日志级别、输出目录、LLM 全局默认参数）
  - `config/game_config.yaml`：游戏配置（游戏类型、玩家数量、每个玩家的模型/性格/外貌）
  - `.env.example`：环境变量示例文件（API key 等敏感信息通过 .env 注入）
  - LLM 配置继承关系：app_config.llm 为全局默认 → game_config 玩家级配置缺省时自动继承
  - 配置项支持 Pydantic 校验，非法配置启动时即报错
- Error handling: 配置文件缺失或格式错误时抛出明确异常并提示修正方式
- Edge cases: .env > 环境变量 > YAML 中的值

### F-03 Logging Module

统一的日志管理。

- Main flow:
  - `core/logging.py`：基于 Python logging 的统一日志配置
  - 支持按模块分 logger（engine、agent、orchestrator、api 等）
  - 日志格式：`[时间] [级别] [模块] 消息`
  - 日志输出：console + 文件（`logs/` 目录）
  - 日志级别通过配置文件控制
- Error handling: 日志目录不存在时自动创建
- Edge cases: N/A

### F-04 Engine Base Class & Game Registry

游戏引擎基类与注册机制。

- Main flow:
  - `engine/base.py`：定义 `GameEngine` 抽象基类，核心方法：
    - `setup(players, config)` — 初始化游戏，分配身份
    - `get_public_state()` — 返回公共信息
    - `get_private_info(player_id)` — 返回玩家私有信息
    - `get_available_actions(player_id)` — 返回可执行操作
    - `apply_action(player_id, action)` — 执行操作，推进状态
    - `get_current_player()` — 返回当前行动玩家
    - `is_ended()` — 判断游戏是否结束
    - `get_result()` — 返回胜负结果
    - `get_game_rules_prompt()` — 返回游戏规则 prompt（供 Agent 使用）
    - `get_tools_schema()` — 返回当前游戏的 tools 定义（供 Agent function calling）
    - `get_agent_strategy()` — 返回游戏专属的 Agent 策略配置（各节点 prompt 模板）
  - `engine/registry.py`：游戏注册表（registry pattern）
    - 装饰器 `@register_game("spy")` 注册游戏
    - `get_game_engine(game_type)` 按名称获取引擎类
    - `list_games()` 列出所有已注册游戏
  - `engine/models.py`：通用数据模型（Action、PlayerState 等 Pydantic model）
- Error handling:
  - 非法 action 抛出 `IllegalActionError`
  - 未注册的游戏类型抛出 `GameNotFoundError`
- Edge cases:
  - 重复注册同名游戏：后注册覆盖前注册，日志 warning

### F-05 Spy Game Engine

谁是卧底游戏引擎实现。

- Main flow:
  - `engine/spy/game.py`：继承 `GameEngine`
  - `engine/spy/prompts.py`：游戏规则 prompt 模板（中文），包含规则说明、发言策略建议等
  - `engine/spy/words.py`：词库管理（内置默认词对列表）
  - `engine/spy/strategy.py`：游戏专属 Agent 策略配置（各节点的 prompt 模板、评估标准）
  - 游戏流程（状态机）：
    - `WAITING` → `setup()` → `SPEAKING`
    - `SPEAKING`：玩家按顺序发言（`speak` action）→ 所有人发言完 → `VOTING`
    - `VOTING`：所有存活玩家投票（`vote` action）→ 统计票数 → `ELIMINATING`
    - `ELIMINATING`：票数最多者淘汰 → 检查胜负 → `ENDED` 或回到 `SPEAKING`
  - 词语分配：从词库随机选词对，随机分配平民词/卧底词
  - 投票规则：票数最多者淘汰；平票无人淘汰
  - 胜负判定：卧底被淘汰 → 平民胜；卧底存活到最后 2 人 → 卧底胜
  - Tools 定义：`speak`、`vote`（`defend` 暂不实现，后续迭代）
- Error handling:
  - 玩家数不足（< 3）：拒绝 setup
  - 已淘汰玩家尝试操作：拒绝
- Edge cases:
  - 所有人投票给同一人（正常淘汰）
  - 多人平票（无人淘汰，进入下一轮发言）

### F-06 Agent Player Framework

LLM 玩家框架。每个 PlayerAgent 对外是单一接口，内部使用 LangGraph 编排多个子节点协作决策。Agent 框架是通用的，游戏专属的策略（各节点 prompt）由 Engine 的 strategy 提供，确保新增游戏时 Agent 代码零修改。

- Main flow:
  - `agent/player.py`：`PlayerAgent` 类
    - 持有 player_id、model 配置、system_prompt（性格策略）
    - `think_and_act(game_context, available_tools, strategy)` → 内部调用 LangGraph 工作流，返回 action
    - strategy 参数由 Orchestrator 从 Engine 获取后传入
  - `agent/graph.py`：LangGraph 工作流定义
    - 定义决策图：Thinker → Evaluator → Optimizer → Output
    - 支持条件边：Evaluator 评分不通过可回到 Thinker 重新分析
    - 节点的 prompt 从 AgentStrategy 读取，不写死
  - `agent/nodes/`：各决策子节点（通用实现，prompt 从外部注入）
    - `thinker.py`：通用思考节点，接收游戏专属的分析 prompt
    - `evaluator.py`：通用评估节点，接收游戏专属的评估标准
    - `optimizer.py`：通用优化节点，接收游戏专属的润色要求
  - `agent/strategy.py`：AgentStrategy 数据模型定义（各节点 prompt 模板的容器）
  - `agent/state.py`：LangGraph State 定义（节点间共享状态）
  - `agent/llm_client.py`：LLM 调用封装
    - 统一 OpenAI 兼容 API 格式
    - 支持 function calling / tool use
    - 支持配置不同模型端点和 API key
    - 支持重试和超时
  - `agent/memory.py`：记忆管理
    - `private_memory`：仅自己可见（思考过程）
    - `public_memory`：所有人可见（发言、投票结果）
    - 记忆注入到 LLM 上下文
- Error handling:
  - LLM 调用失败：重试 + 降级（返回默认 action）
  - LLM 返回非法 tool call：解析错误日志 + 重试
  - 子节点循环超限（Evaluator 反复打回）：强制使用当前最佳结果
- Edge cases:
  - LLM 返回多个 tool call：取第一个合法的
  - Evaluator 评分边界：设定阈值，低于阈值重新思考，最多重试 N 次

### F-07 Orchestrator Runner

流程编排器，驱动完整游戏。

- Main flow:
  - `orchestrator/runner.py`：`GameRunner` 类
    - `run(game_config)` → 从配置创建 Engine + Agents → 驱动游戏循环 → 输出剧本
    - 游戏循环：获取当前玩家 → 组装上下文（公共 + 私有 + rules prompt + tools） → Agent 决策 → Engine 执行 → Recorder 记录 → 广播公共结果
    - 支持事件钩子（hook），供 Recorder 和其他观察者挂载
- Error handling:
  - 单个 Agent 异常不中断游戏，记录错误并用默认 action 继续
  - 游戏超时保护（可配置最大轮次）
- Edge cases: N/A

### F-08 Script Module — Schema & Recorder

剧本数据结构与事件记录。

- Main flow:
  - `script/schema.py`：Pydantic 模型
    - `GameScript`：顶层结构（game info、players、rounds、result）
    - `PlayerInfo`：玩家信息（id、name、model、persona、appearance、role、word）
    - `RoundData`：轮次数据（round_number、events、vote_result）
    - `GameEvent`：单个事件（player_id、phase、timestamp、thinking、action、expression、memory_snapshot）
    - `VoteResult`：投票结果（votes map、eliminated）
    - `GameResult`：游戏结果（winner、eliminated_order、total_rounds、duration）
  - `script/recorder.py`：`GameRecorder` 类
    - 观察者模式，通过 Orchestrator 的事件钩子接收事件
    - 记录所有事件（含时间戳、思考耗时）
    - `export()` → 输出完整 `GameScript` 对象，可序列化为 JSON
    - 自动保存到 `scripts/` 目录
- Error handling: 记录失败不影响游戏进行（日志 warning）
- Edge cases: N/A

### F-09 CLI Entry Point & Optional API

主入口为 CLI 直接运行游戏管线，API 为可选模块。

- Main flow:
  - `backend/main.py`：CLI 入口
    - `python -m backend.main` — 使用默认配置运行一局游戏
    - `python -m backend.main --config path/to/game_config.yaml` — 指定配置
    - 运行完毕输出剧本 JSON 路径
  - `api/`：可选的 HTTP 服务（保留，不作为默认入口）
- Error handling:
  - 配置错误：打印错误信息并退出
- Edge cases: N/A

## 4. Non-functional Requirements

- **可扩展性**：新增游戏 = ①新 Engine 子类 + `@register_game` 装饰器 ②游戏规则 prompt 放在游戏模块内 ③其他模块零修改
- **模块解耦**：Engine ↔ Agent ↔ Recorder ↔ API 通过数据模型和接口通信，无直接依赖
- **Python 版本**：3.11+
- **类型标注**：全量 type hints
- **日志**：所有模块使用统一日志框架，关键操作均有日志

## 5. Out of Scope

- ~~Renderer 视频渲染管线（SD 生图、TTS、moviepy）~~ — 预留目录，暂不实现
- ~~Frontend 前端回放~~ — 独立需求处理
- ~~GPT-SoVITS 音色克隆~~ — 暂不实现
- ~~用户认证与权限~~ — 单机使用
- ~~数据库存储~~ — JSON 文件即可
- ~~defend（自辩）action~~ — 后续迭代

## 6. Acceptance Criteria

| ID | Feature | Condition | Expected Result |
|:---|:---|:---|:---|
| AC-01 | F-02 | 启动时加载 config YAML | 配置正确解析为 Pydantic model，非法配置报错 |
| AC-02 | F-03 | 各模块使用 logger | 日志按格式输出到 console 和文件 |
| AC-03 | F-04 | 新游戏用 @register_game 注册 | `get_game_engine("spy")` 返回 SpyGame 类 |
| AC-04 | F-05 | 手动驱动一局谁是卧底 | 完成发言→投票→淘汰→胜负判定全流程 |
| AC-05 | F-05 | 调用 get_game_rules_prompt() | 返回中文游戏规则 prompt |
| AC-06 | F-06 | Agent 调用 LLM 并返回 action | think_and_act 返回合法的 tool call 结果 |
| AC-07 | F-07 | Orchestrator 驱动完整一局游戏 | 从 setup 到 is_ended，输出完整剧本 JSON |
| AC-08 | F-08 | Recorder 记录全过程 | 剧本 JSON 符合 schema，包含所有事件 |
| AC-09 | F-09 | 运行 python -m backend.main | 完成一局游戏并输出剧本 JSON 文件路径 |

## 7. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-14 | Initial version | ALL | - |
| v2 | 2026-03-14 | Agent internal multi-node LangGraph workflow; config/output dirs moved to project root | F-01, F-06 | User feedback: each player should use multi-agent collaboration internally; config/output files at root level |
| v3 | 2026-03-14 | Agent strategy injection from engine; common→core; CLI entry; LLM config inheritance; .env.example | F-01, F-02, F-03, F-05, F-06, F-09 | User feedback: agent nodes not pluggable per game; no need for HTTP server; duplicate LLM config |
