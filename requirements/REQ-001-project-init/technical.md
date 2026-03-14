# REQ-001 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-14
> Updated: 2026-03-14

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Runtime | Python 3.11+ | match type hints, asyncio improvements |
| Package Manager | uv + pyproject.toml | fast, modern Python packaging |
| Web Framework | FastAPI + uvicorn | async native, auto OpenAPI docs |
| Data Validation | Pydantic v2 | config, schema, API models unified |
| LLM Client | openai (Python SDK) | OpenAI-compatible API, function calling support |
| Agent Orchestration | langgraph | Multi-node decision workflow inside each player agent |
| TTS (reserved) | edge-tts | free, fast, multi-voice Chinese support |
| Image Gen (reserved) | diffusers + torch | local SDXL, no API dependency |
| Video (reserved) | moviepy + Pillow | Python native compositing |
| Logging | Python logging (stdlib) | zero dependency, flexible handlers |
| Config | PyYAML + pydantic-settings | YAML + env var overlay |
| Testing | pytest + pytest-asyncio | async test support |

## 2. Design Principles

- **高内聚低耦合**：模块间通过抽象接口和 Pydantic 数据模型通信，无直接实例依赖
- **数据契约驱动**：Engine ↔ Agent ↔ Recorder 之间以 Pydantic model 为契约，剧本 JSON 是唯一的跨管线数据格式
- **即插即用**：新游戏 = 1 个 Engine 子类 + `@register_game` 装饰器 + 游戏专属 prompts/words 文件，零改动已有代码
- **异步优先**：Agent LLM 调用、API 接口均为 async，Engine 保持同步（纯计算无 IO）
- **失败隔离**：单个 Agent 异常不中断游戏，Recorder 异常不影响游戏逻辑

## 3. Architecture Overview

```
Masquerade/
├── backend/                # Python 源码
│   ├── engine/             # 游戏引擎层 — 纯规则，不依赖 LLM
│   ├── agent/              # AI 玩家层 — 内部 LangGraph 多节点协作
│   ├── orchestrator/       # 编排层 — 连接 Engine + Agent，驱动游戏
│   ├── script/             # 剧本层 — 数据模型 + 事件记录
│   ├── api/                # API 层 — HTTP 接口
│   ├── common/             # 公共层 — 日志、异常、工具函数
│   └── renderer/           # 视频渲染（预留）
├── config/                 # 配置文件（项目根）
├── scripts/                # 剧本 JSON 输出
├── output/                 # 视频输出（预留）
├── logs/                   # 日志输出
├── assets/                 # 素材（预留）
└── models/                 # SD 模型（预留）
```

层间依赖关系（单向）：

```
API → Orchestrator → Engine
                   → Agent (内部: LangGraph workflow)
                   → Script (Recorder)
Engine → common (exceptions, models)
Agent  → common (exceptions), langgraph
Script → common
config/ → (项目根，被所有模块引用)
```

（详见 tech-architecture.puml）

## 4. Module Design

### 4.1 common/ — 公共模块

- **Responsibility**: 提供跨模块共享的基础设施
- **Public interface**:
  - `common/logging.py`
    - `setup_logging(level: str, log_dir: str)` — 初始化日志系统（应用启动时调用一次）
    - `get_logger(name: str) -> Logger` — 获取模块级 logger
    - Handler: `StreamHandler`(console) + `RotatingFileHandler`(file)
    - Format: `[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s`
  - `common/exceptions.py`
    - `MasqueradeError` — 基类
    - `IllegalActionError` — Engine 层非法操作
    - `GameNotFoundError` — Registry 查无此游戏
    - `LLMClientError` — LLM 调用失败
    - `ConfigError` — 配置解析失败
- **Internal structure**: 纯工具函数和异常定义，无状态
- **Reuse notes**: 所有模块 import，是唯一允许被所有层依赖的模块

### 4.2 config/ — 配置模块（项目根目录）

- **Responsibility**: 统一管理应用配置和游戏配置。配置文件放在项目根 `config/` 目录，Pydantic 解析逻辑放在 `backend/common/config.py`
- **Public interface**:
  - `backend/common/config.py` — 配置解析逻辑
    - `AppSettings(BaseSettings)` — 应用配置（api_host, api_port, log_level, log_dir, llm defaults）
    - `PlayerConfig(BaseModel)` — 单个玩家配置（name, model, api_base, api_key, persona, appearance）
    - `GameConfig(BaseModel)` — 游戏配置（game_type, player_count, spy_count, players: list[PlayerConfig], max_rounds）
    - `load_app_settings(path: str) -> AppSettings`
    - `load_game_config(path: str) -> GameConfig`
  - `config/app_config.yaml` — 应用配置示例（项目根）
  - `config/game_config.yaml` — 游戏配置示例（项目根）
- **Internal structure**:
  - YAML 文件在项目根 `config/`，Python 解析代码在 `backend/common/config.py`
  - Pydantic Settings 从 YAML 加载，env var 可覆盖（前缀 `MASQUERADE_`）
  - YAML 解析用 PyYAML
- **Reuse notes**: 被 API、Orchestrator 引用

### 4.3 engine/ — 游戏引擎模块

- **Responsibility**: 定义游戏规则，管理游戏状态，校验操作合法性。不依赖 LLM，可接人类玩家
- **Public interface**:
  - `engine/base.py` — `GameEngine` 抽象基类

    ```python
    class GameEngine(ABC):
        @abstractmethod
        def setup(self, players: list[str], config: dict) -> None: ...
        @abstractmethod
        def get_public_state(self) -> dict: ...
        @abstractmethod
        def get_private_info(self, player_id: str) -> dict: ...
        @abstractmethod
        def get_available_actions(self, player_id: str) -> list[str]: ...
        @abstractmethod
        def apply_action(self, player_id: str, action: Action) -> ActionResult: ...
        @abstractmethod
        def get_current_player(self) -> str | None: ...
        @abstractmethod
        def is_ended(self) -> bool: ...
        @abstractmethod
        def get_result(self) -> GameResult | None: ...
        @abstractmethod
        def get_game_rules_prompt(self) -> str: ...
        @abstractmethod
        def get_tools_schema(self) -> list[dict]: ...
    ```

  - `engine/models.py` — 引擎层数据模型

    ```python
    class Action(BaseModel):
        type: str              # "speak" | "vote"
        player_id: str
        payload: dict          # {"content": "..."} or {"target_player_id": "..."}

    class ActionResult(BaseModel):
        success: bool
        message: str
        public_info: dict | None   # 广播给所有人的信息

    class GameResult(BaseModel):
        winner: str            # "civilian" | "spy"
        eliminated_order: list[str]
        total_rounds: int
    ```

  - `engine/registry.py` — 注册表

    ```python
    _REGISTRY: dict[str, type[GameEngine]] = {}

    def register_game(name: str):
        """Decorator: @register_game("spy")"""
        def decorator(cls): ...

    def get_game_engine(name: str) -> type[GameEngine]: ...
    def list_games() -> list[str]: ...
    ```

- **Internal structure**:
  - `engine/spy/` — 谁是卧底子包
    - `game.py` — `SpyGame(GameEngine)` 实现
    - `prompts.py` — 游戏规则 prompt 模板
    - `words.py` — 词对库（内置 list[tuple[str,str]]）
    - `__init__.py` — import SpyGame 触发 @register_game 注册
  - 状态机用 `enum.Enum`（`GamePhase: WAITING, SPEAKING, VOTING, ELIMINATING, ENDED`）
  - 新游戏：在 `engine/` 下新建子包，继承 `GameEngine` + 装饰器注册即可
- **Reuse notes**: `base.py`、`models.py`、`registry.py` 被所有游戏子包和 Orchestrator 复用

### 4.4 agent/ — AI 玩家模块

- **Responsibility**: 封装 LLM 交互，管理玩家记忆，产出决策。不知道具体游戏规则。每个 PlayerAgent 对外是单一接口，内部使用 LangGraph 编排多个决策子节点协作。
- **Public interface**:
  - `agent/player.py` — `PlayerAgent`（对外唯一接口）

    ```python
    class PlayerAgent:
        def __init__(self, player_id: str, config: PlayerConfig): ...

        async def think_and_act(
            self,
            game_rules_prompt: str,
            public_state: dict,
            private_info: dict,
            available_actions: list[str],
            tools_schema: list[dict],
        ) -> AgentResponse:
            """内部调用 LangGraph 工作流，对外只返回最终结果"""
            ...

        def update_public_memory(self, event_summary: str) -> None: ...
    ```

  - `agent/graph.py` — LangGraph 工作流定义

    ```python
    from langgraph.graph import StateGraph

    def build_player_graph() -> StateGraph:
        """
        构建玩家决策图:
        Thinker → Evaluator →(pass)→ Optimizer → Output
                            →(fail)→ Thinker (retry, max N times)
        """
        graph = StateGraph(AgentState)
        graph.add_node("thinker", thinker_node)
        graph.add_node("evaluator", evaluator_node)
        graph.add_node("optimizer", optimizer_node)
        graph.add_conditional_edges(
            "evaluator",
            should_retry,
            {"retry": "thinker", "proceed": "optimizer"}
        )
        return graph.compile()
    ```

  - `agent/state.py` — LangGraph State 定义

    ```python
    class AgentState(TypedDict):
        # Input context
        game_rules_prompt: str
        public_state: dict
        private_info: dict
        available_actions: list[str]
        tools_schema: list[dict]
        persona: str
        memory_context: list[dict]

        # Thinker output
        situation_analysis: str
        strategy: str

        # Evaluator output
        evaluation_score: float
        evaluation_feedback: str
        retry_count: int

        # Optimizer output
        optimized_content: str
        expression: str

        # Final output
        action: Action
        thinking: str
        thinking_duration_ms: int
    ```

  - `agent/nodes/thinker.py` — 思考节点

    ```python
    async def thinker_node(state: AgentState) -> dict:
        """分析局势，推理其他玩家身份，生成策略"""
        # 用推理能力强的模型
        ...
    ```

  - `agent/nodes/evaluator.py` — 评估节点

    ```python
    async def evaluator_node(state: AgentState) -> dict:
        """评估策略可行性，打分，判断是否需要重新思考"""
        ...

    def should_retry(state: AgentState) -> str:
        """条件边：评分 < 阈值且重试次数 < max → retry，否则 proceed"""
        ...
    ```

  - `agent/nodes/optimizer.py` — 优化节点

    ```python
    async def optimizer_node(state: AgentState) -> dict:
        """优化发言表达，使其更自然、更符合人设"""
        ...
    ```

  - `agent/models.py` — Agent 层数据模型

    ```python
    class AgentResponse(BaseModel):
        thinking: str          # 完整思考链（含分析+评估+优化过程）
        action: Action         # 最终公开操作
        expression: str        # 表情标签
        thinking_duration_ms: int
    ```

  - `agent/llm_client.py` — `LLMClient`

    ```python
    class LLMClient:
        def __init__(self, model: str, api_base: str, api_key: str): ...

        async def chat_with_tools(
            self,
            messages: list[dict],
            tools: list[dict] | None = None,
            temperature: float = 0.7,
        ) -> LLMResponse: ...

        async def chat(
            self,
            messages: list[dict],
            temperature: float = 0.7,
        ) -> str:
            """纯文本对话（用于 Evaluator 等不需要 tool call 的节点）"""
            ...
    ```

  - `agent/memory.py` — `PlayerMemory`

    ```python
    class PlayerMemory:
        private_memory: list[str]
        public_memory: list[str]

        def add_private(self, content: str) -> None: ...
        def add_public(self, content: str) -> None: ...
        def build_context_messages(self) -> list[dict]: ...
    ```

- **Internal structure**:
  - `player.py`：对外门面，构建 LangGraph 输入状态，调用 graph，解析输出
  - `graph.py`：工作流拓扑定义
  - `nodes/`：各决策节点独立文件，可单独测试
  - `state.py`：共享状态结构
  - 不同节点可配置不同模型（如 Thinker 用强推理模型，Evaluator 用快速模型）
- **Reuse notes**: `LLMClient` 可被其他需要 LLM 的模块复用；`graph.py` 的图结构可为不同游戏定制不同决策流（通过配置）

### 4.5 script/ — 剧本模块

- **Responsibility**: 定义剧本数据结构，记录游戏全过程
- **Public interface**:
  - `script/schema.py` — Pydantic 数据模型

    ```python
    class GameScript(BaseModel):
        game: GameInfo
        players: list[PlayerInfo]
        rounds: list[RoundData]
        result: GameResult | None

    class GameInfo(BaseModel):
        type: str
        config: dict
        created_at: datetime

    class PlayerInfo(BaseModel):
        id: str
        name: str
        model: str
        persona: str
        appearance: str
        role: str
        word: str

    class GameEvent(BaseModel):
        player_id: str
        phase: str
        timestamp: datetime
        thinking_duration_ms: int
        thinking: str
        expression: str
        action: Action
        memory_snapshot: MemorySnapshot

    class RoundData(BaseModel):
        round_number: int
        events: list[GameEvent]
        vote_result: VoteResult | None

    class VoteResult(BaseModel):
        votes: dict[str, str]
        eliminated: str | None
    ```

  - `script/recorder.py` — `GameRecorder`

    ```python
    class GameRecorder:
        def __init__(self, game_info: GameInfo, players: list[PlayerInfo]): ...
        def start_round(self, round_number: int) -> None: ...
        def record_event(self, event: GameEvent) -> None: ...
        def record_vote_result(self, result: VoteResult) -> None: ...
        def set_result(self, result: GameResult) -> None: ...
        def export(self) -> GameScript: ...
        def save(self, output_dir: str) -> str: ...  # returns file path
    ```

- **Internal structure**: schema.py 纯数据定义，recorder.py 有状态（当前轮次、事件列表）
- **Reuse notes**: `schema.py` 是跨管线的数据契约，被 Orchestrator、API、未来的 Renderer/Frontend 共用

### 4.6 orchestrator/ — 编排模块

- **Responsibility**: 连接 Engine 和 Agent，驱动完整游戏循环
- **Public interface**:
  - `orchestrator/runner.py` — `GameRunner`

    ```python
    class GameRunner:
        def __init__(self, game_config: GameConfig): ...

        async def run(self) -> GameScript:
            """
            1. Registry 获取 Engine 类，实例化并 setup
            2. 为每个玩家创建 PlayerAgent
            3. 创建 GameRecorder
            4. 循环驱动：Engine.get_current_player → 组装上下文 → Agent.think_and_act → Engine.apply_action → Recorder.record
            5. 游戏结束 → Recorder.export → 保存并返回 GameScript
            """

        def _build_agent_context(self, player_id: str) -> dict:
            """组装传给 Agent 的完整上下文"""
    ```

  - `orchestrator/event_bus.py` — 简易事件总线

    ```python
    class EventBus:
        def subscribe(self, event_type: str, callback: Callable) -> None: ...
        def emit(self, event_type: str, data: Any) -> None: ...
    ```

    事件类型：`game_start`, `round_start`, `player_speak`, `player_vote`, `player_eliminated`, `game_end`

- **Internal structure**: runner.py 是核心，event_bus.py 支撑观察者模式
- **Reuse notes**: `EventBus` 可用于任何需要事件发布订阅的场景

### 4.7 api/ — API 模块

- **Responsibility**: HTTP 接口层，接收请求，调用 Orchestrator
- **Public interface**:
  - `api/main.py` — FastAPI app 创建 + 路由注册
  - `api/routes/games.py` — 游戏相关路由

    ```
    POST   /api/v1/games           → 创建游戏，返回 game_id
    GET    /api/v1/games/{id}      → 查询游戏状态
    GET    /api/v1/games/{id}/script → 获取剧本 JSON
    GET    /api/v1/scripts         → 列出历史剧本
    ```

  - `api/models.py` — 请求/响应 Pydantic model

    ```python
    class CreateGameRequest(BaseModel):
        game_type: str = "spy"
        player_count: int = 4
        spy_count: int = 1
        players: list[PlayerConfig] | None = None  # None = use default config

    class GameStatusResponse(BaseModel):
        game_id: str
        status: str   # "running" | "completed" | "error"
        created_at: datetime
        error: str | None = None

    class ScriptListResponse(BaseModel):
        scripts: list[ScriptSummary]
    ```

  - `api/game_manager.py` — 游戏生命周期管理

    ```python
    class GameManager:
        """管理运行中和已完成的游戏实例"""
        async def create_and_run(self, request: CreateGameRequest) -> str: ...
        def get_status(self, game_id: str) -> GameStatusResponse: ...
        def get_script(self, game_id: str) -> GameScript | None: ...
        def list_scripts(self) -> list[ScriptSummary]: ...
    ```

- **Internal structure**:
  - `main.py`：创建 FastAPI app，注册路由，startup 时初始化 config/logging
  - `routes/`：按资源分文件
  - `game_manager.py`：内存存储游戏状态（dict），异步运行游戏任务
- **Reuse notes**: `api/models.py` 仅 API 层使用，不被其他模块引用

## 5. Data Model

核心数据流：

```
GameConfig (config/)
    ↓ [input]
Engine (engine/) ←→ Action / ActionResult (engine/models.py)
    ↓ [state changes]
AgentResponse (agent/models.py)
    ↓ [recorded by]
GameEvent → RoundData → GameScript (script/schema.py)
    ↓ [serialized]
script JSON file (scripts/)
    ↓ [served by]
API response (api/models.py)
```

模型分布原则：
- **engine/models.py**：Action、ActionResult、GameResult — 游戏操作相关
- **agent/models.py**：AgentResponse — LLM 输出相关
- **script/schema.py**：GameScript 及其子结构 — 剧本序列化相关
- **api/models.py**：Request/Response — HTTP 接口相关
- **config/settings.py**：AppSettings、GameConfig、PlayerConfig — 配置相关

各层模型独立定义，通过 Orchestrator 做转换，避免跨层直接引用内部模型。

（详见 tech-class.puml）

## 6. API Design

| Method | Path | Request | Response | Description |
|:---|:---|:---|:---|:---|
| POST | `/api/v1/games` | `CreateGameRequest` body | `{"game_id": "xxx"}` 202 | 创建并异步运行游戏 |
| GET | `/api/v1/games/{id}` | - | `GameStatusResponse` 200 / 404 | 查询游戏状态 |
| GET | `/api/v1/games/{id}/script` | - | `GameScript` JSON 200 / 404 / 202(running) | 获取完整剧本 |
| GET | `/api/v1/scripts` | `?page=1&size=20` | `ScriptListResponse` 200 | 列出历史剧本 |

API 路由前缀 `/api/v1/`，为未来版本升级预留。

## 7. Key Flows

### 7.1 Complete Game Flow

（详见 tech-sequence.puml）

1. API 收到 `POST /games` → 创建 `GameRunner`
2. `GameRunner.run()` 异步执行：
   - 从 Registry 获取 Engine → `setup()`
   - 创建 PlayerAgent 实例（每个玩家一个）
   - 创建 GameRecorder
   - 进入循环：
     - `Engine.get_current_player()` → 获取当前玩家
     - 组装上下文（rules prompt + public state + private info + tools）
     - `Agent.think_and_act()` → 获取 AgentResponse
     - `Engine.apply_action()` → 获取 ActionResult
     - `Recorder.record_event()` → 记录事件
     - 广播公共信息到所有 Agent 的 public_memory
   - 游戏结束 → `Recorder.export()` → 保存 JSON
3. API 轮询 `GET /games/{id}` 获取状态

### 7.2 Single Agent Turn Flow

1. Orchestrator 组装 messages:
   - system: game rules prompt + persona prompt
   - history: public_memory + private_memory (via `PlayerMemory.build_context_messages()`)
   - user: current state + "please make your move"
2. `LLMClient.chat_with_tools(messages, tools)` → LLM 返回 thinking + tool_call
3. 解析 tool_call → 构建 `Action`
4. 返回 `AgentResponse(thinking, action, expression, duration)`

### 7.3 New Game Plugin Flow

```
1. Create engine/new_game/__init__.py
2. Create engine/new_game/game.py:
     @register_game("new_game")
     class NewGameEngine(GameEngine):
         def get_game_rules_prompt(self) -> str: ...
         def get_tools_schema(self) -> list[dict]: ...
         # ... implement all abstract methods
3. Create engine/new_game/prompts.py — game rules prompt
4. Import in engine/__init__.py (or auto-discover)
5. Done — Orchestrator/Agent/Recorder work unchanged
```

## 8. Shared Modules & Reuse Strategy

| Shared Component | Location | Used By |
|:---|:---|:---|
| Logging | `common/logging.py` | ALL modules |
| Exceptions | `common/exceptions.py` | ALL modules |
| GameEngine ABC | `engine/base.py` | All game engine subclasses |
| Engine Models (Action, etc.) | `engine/models.py` | engine/, orchestrator/, script/ |
| Game Registry | `engine/registry.py` | engine subpackages, orchestrator/ |
| Script Schema | `script/schema.py` | orchestrator/, api/, future renderer/ |
| LLMClient | `agent/llm_client.py` | agent/, future modules needing LLM |
| EventBus | `orchestrator/event_bus.py` | orchestrator/, script/recorder |
| Config Models | `config/settings.py` | api/, orchestrator/ |

**模型隔离规则**：
- engine/models.py ← orchestrator 可引用
- agent/models.py ← orchestrator 可引用
- script/schema.py ← api, orchestrator 可引用
- api/models.py ← 仅 api 内部使用
- **禁止反向依赖**（如 engine 引用 agent 的模型）

## 9. Risks & Notes

| Risk | Impact | Mitigation |
|:---|:---|:---|
| LLM 返回格式不稳定 | Agent 解析失败 | 重试 + 降级默认 action + 详细日志 |
| 不同 LLM 的 function calling 能力差异 | 某些模型无法正确调用 tools | LLMClient 层做适配，支持 fallback 到 prompt-based |
| 游戏死循环（持续平票） | 游戏无法结束 | max_rounds 配置，超限强制结束 |
| 内存游戏状态丢失（进程重启） | 运行中的游戏丢失 | 当前阶段可接受，后续可加持久化 |

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-14 | Initial version | ALL | - |
| v2 | 2026-03-14 | Agent module uses LangGraph multi-node workflow internally; config/output dirs moved to project root | Module 4.2, Module 4.4, Section 1, Section 3 | User feedback: multi-agent collaboration inside each player; config/output at root level |
