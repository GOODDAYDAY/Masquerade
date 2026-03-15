# REQ-006 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Game Engine | Python 3.12 + Pydantic | 与现有 SpyGame 保持一致 |
| Agent Framework | LangGraph (unchanged) | 不修改，通过策略注入适配 |
| Script Recording | Pydantic models (unchanged) | 不修改核心结构 |
| Configuration | YAML | 与现有 config 体系一致 |

## 2. Design Principles

- **高内聚、低耦合：** Runner 仅依赖 GameEngine 抽象接口，不依赖任何具体游戏模块
- **复用优先：** 基类提供默认实现，具体游戏仅覆写差异化方法
- **扩展点清晰：** 新增游戏仅需：① 创建 engine 子模块 ② 注册到 registry ③ 添加配置文件
- **向后兼容：** GameEngine 新增方法提供默认实现，避免破坏现有 SpyGame

## 3. Architecture Overview

架构分层不变，改动集中在两处：

1. **GameEngine 基类扩展** — 新增 5 个方法（带默认实现），修改 `get_agent_strategy` 签名
2. **GameRunner 重构** — 移除所有 Spy 硬编码，改用 Engine 接口驱动
3. **新增 WerewolfGame 模块** — 仅在 `backend/engine/werewolf/` 下

```
backend/
├── engine/
│   ├── base.py              ← 扩展接口（+5 methods, 1 signature change）
│   ├── models.py            ← 不变
│   ├── registry.py          ← 不变
│   ├── __init__.py          ← +1 行 import werewolf
│   ├── spy/                 ← 适配新接口（小改动）
│   │   ├── game.py          ← 更新 get_agent_strategy 签名
│   │   ├── strategy.py      ← 不变
│   │   └── prompts.py       ← 不变
│   └── werewolf/            ← 新增模块
│       ├── __init__.py
│       ├── game.py           ← WerewolfGame(GameEngine) 主状态机
│       ├── strategy.py       ← 6 种角色策略 prompts
│       └── prompts.py        ← 游戏规则 prompt
├── orchestrator/
│   └── runner.py            ← 重构，移除 spy 耦合
└── (其余不变)
```

## 4. Module Design

### 4.1 GameEngine 基类扩展

**文件：** `backend/engine/base.py`

**修改 1：** `get_agent_strategy` 签名变更

```python
# Before:
def get_agent_strategy(self) -> AgentStrategy

# After:
@abstractmethod
def get_agent_strategy(self, player_id: str) -> AgentStrategy:
    """Return game-specific strategy for this player (may vary by role)."""
```

**修改 2：** 新增 5 个方法（带默认实现，非 abstract）

```python
def format_action_log(self, player_id: str, action: Action) -> str:
    """Format action for console logging. Override for game-specific formatting."""
    return "%s: %s" % (player_id, action.type)

def get_broadcast_targets(self, player_id: str, action: Action) -> list[str] | None:
    """Which players should receive this action's public summary.
    Returns None = all players, [] = nobody, [ids] = specific players."""
    return None

def format_public_summary(self, player_id: str, action: Action) -> str:
    """Format action as a text summary for broadcasting to players' memory."""
    return "%s 执行了 %s" % (player_id, action.type)

def get_round_end_summary(self, round_number: int) -> str | None:
    """Return text summary to broadcast to all players at end of round.
    Used for vote results, night death announcements, etc."""
    return None

def get_vote_result(self, round_number: int) -> dict | None:
    """Return vote result data for this round for script recording.
    Returns {votes: {voter: target}, eliminated: str|None} or None."""
    return None
```

**设计决策：** 使用默认实现而非 abstract，确保：
- 现有 SpyGame 只需适配 `get_agent_strategy` 签名变更即可编译
- SpyGame 可选覆写其他方法以提供更好的日志/广播行为
- 未来新游戏有开箱即用的默认行为

### 4.2 SpyGame 适配

**文件：** `backend/engine/spy/game.py`

仅需以下适配：

1. **`get_agent_strategy(self, player_id: str)`** — 将 Runner 中的 blank 策略选择逻辑移入：
   ```python
   def get_agent_strategy(self, player_id: str) -> AgentStrategy:
       ps = self.players.get(player_id)
       if ps and ps.role == "blank":
           return get_blank_strategy()
       return get_spy_strategy()
   ```

2. **覆写 `format_action_log`** — 提供 Spy 游戏的友好日志格式：
   ```python
   def format_action_log(self, player_id: str, action: Action) -> str:
       if action.type == "speak":
           return "[%s] %s says: %s" % (self.phase.value, player_id, action.payload.get("content", ""))
       if action.type == "vote":
           return "[%s] %s votes for: %s" % (self.phase.value, player_id, action.payload.get("target_player_id", ""))
       return "%s: %s" % (player_id, action.type)
   ```

3. **覆写 `get_broadcast_targets`** — 投票不广播：
   ```python
   def get_broadcast_targets(self, player_id: str, action: Action) -> list[str] | None:
       if action.type == "vote":
           return []  # secret ballot
       return None  # broadcast to all
   ```

4. **覆写 `format_public_summary`** — 发言摘要：
   ```python
   def format_public_summary(self, player_id: str, action: Action) -> str:
       if action.type == "speak":
           return "%s 说: %s" % (player_id, action.payload.get("content", ""))
       return "%s 执行了 %s" % (player_id, action.type)
   ```

5. **覆写 `get_round_end_summary`** — 投票结果广播：
   ```python
   def get_round_end_summary(self, round_number: int) -> str | None:
       votes = self.vote_history.get(round_number, {})
       if not votes:
           return None
       # ... format vote summary (move from runner)
   ```

6. **覆写 `get_vote_result`** — 投票数据供录制：
   ```python
   def get_vote_result(self, round_number: int) -> dict | None:
       votes = self.vote_history.get(round_number, {})
       if not votes:
           return None
       # find eliminated player for this round
       return {"votes": votes, "eliminated": ...}
   ```

### 4.3 GameRunner 重构

**文件：** `backend/orchestrator/runner.py`

**核心变更：移除所有 `backend.engine.spy` 导入和 Spy 特定逻辑**

重构后的 Runner 游戏循环：

```python
async def run(self) -> GameScript:
    # 1. Setup (unchanged pattern)
    engine = get_game_engine(self.game_type)()
    engine.setup(player_ids, self.game_config)

    # 2. Create agents (unchanged)
    agents = {pc.name: PlayerAgent(player_id=pc.name, config=pc) for pc in player_configs}

    # 3. Game loop — fully engine-driven
    while not engine.is_ended():
        public_state = engine.get_public_state()
        current_round = public_state.get("round_number", round_count + 1)
        recorder.start_round(current_round)

        while engine.get_current_player() and not engine.is_ended():
            if engine.get_public_state().get("round_number") != current_round:
                break

            player_id = engine.get_current_player()
            phase = engine.get_public_state().get("phase", "")

            # Strategy from engine (role-aware)
            strategy = engine.get_agent_strategy(player_id)

            # Agent turn
            response = await self._agent_turn(engine, agents[player_id], player_id, strategy)

            # Logging via engine
            log_msg = engine.format_action_log(player_id, response.action)
            logger.info(log_msg)

            # Record event
            recorder.record_event(self._build_event(player_id, response, agents[player_id], phase))

            # Broadcast via engine
            targets = engine.get_broadcast_targets(player_id, response.action)
            if targets is None:
                targets = list(agents.keys())
            if targets:
                summary = engine.format_public_summary(player_id, response.action)
                for pid in targets:
                    if pid in agents:
                        agents[pid].update_public_memory(summary)

        # Round-end: vote result recording
        vote_data = engine.get_vote_result(current_round)
        if vote_data:
            recorder.record_vote_result(VoteResult(
                votes=vote_data.get("votes", {}),
                eliminated=vote_data.get("eliminated"),
            ))

        # Round-end: summary broadcast
        round_summary = engine.get_round_end_summary(current_round)
        if round_summary:
            for agent in agents.values():
                agent.update_public_memory(round_summary)
```

**删除的代码：**
- `from backend.engine.spy.strategy import get_blank_strategy` — 移入 SpyGame
- `blank_strategy = get_blank_strategy() if ...` — 移入 SpyGame
- `active_strategy = blank_strategy if ...` — 由 `engine.get_agent_strategy(player_id)` 替代
- `if action.type == "speak" / "vote"` 日志 — 由 `engine.format_action_log()` 替代
- `if action.type != "vote"` 广播判断 — 由 `engine.get_broadcast_targets()` 替代
- `self._format_public_summary()` — 由 `engine.format_public_summary()` 替代
- 投票结果提取（L157-179） — 由 `engine.get_vote_result()` + `engine.get_round_end_summary()` 替代

### 4.4 WerewolfGame 引擎

**文件：** `backend/engine/werewolf/game.py`

#### 4.4.1 Phase 状态机

```python
class WerewolfPhase(str, Enum):
    WAITING = "waiting"
    NIGHT_GUARD = "night_guard"
    NIGHT_WOLF_DISCUSS = "night_wolf_discuss"
    NIGHT_WOLF_KILL = "night_wolf_kill"
    NIGHT_WITCH = "night_witch"
    NIGHT_SEER = "night_seer"
    DAY_ANNOUNCE = "day_announce"
    DAY_LAST_WORDS = "day_last_words"
    DAY_HUNTER = "day_hunter"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTING = "day_voting"
    ENDED = "ended"
```

Phase 转换流程：
```
WAITING → NIGHT_GUARD → NIGHT_WOLF_DISCUSS (2 rounds) → NIGHT_WOLF_KILL
→ NIGHT_WITCH → NIGHT_SEER → [night resolve + win check]
→ DAY_ANNOUNCE → DAY_LAST_WORDS → DAY_HUNTER (if hunter died)
→ DAY_DISCUSSION → DAY_VOTING → [vote resolve + win check]
→ NIGHT_GUARD (next round) ... → ENDED
```

跳过规则：
- 守卫已死 → 跳过 NIGHT_GUARD
- 无存活狼人 → 跳过 NIGHT_WOLF_*（不应出现，因为已结束）
- 女巫已死或无药可用 → 跳过 NIGHT_WITCH
- 预言家已死 → 跳过 NIGHT_SEER
- 无人死亡 → 跳过 DAY_LAST_WORDS
- 死者非猎人或猎人不开枪 → 跳过 DAY_HUNTER

#### 4.4.2 核心状态

```python
class WerewolfGame(GameEngine):
    def __init__(self):
        self.phase: WerewolfPhase = WerewolfPhase.WAITING
        self.players: dict[str, PlayerState] = {}
        self.player_order: list[str] = []
        self.round_number: int = 0

        # Role tracking
        self.wolf_ids: list[str] = []
        self.seer_id: str | None = None
        self.witch_id: str | None = None
        self.hunter_id: str | None = None
        self.guard_id: str | None = None

        # Witch resources (whole game)
        self.witch_antidote_used: bool = False
        self.witch_poison_used: bool = False

        # Guard state
        self.guard_last_protected: str | None = None

        # Seer knowledge
        self.seer_results: dict[str, str] = {}  # player_id -> "village"/"wolf"

        # Night state (reset each night)
        self.night_guard_target: str | None = None
        self.night_wolf_target: str | None = None
        self.night_witch_save: bool = False
        self.night_witch_poison_target: str | None = None

        # Wolf discussion state
        self.wolf_discuss_round: int = 0      # current discussion round (1 or 2)
        self.wolf_discuss_idx: int = 0        # current wolf index in discussion
        self.wolf_discussions: list[dict] = []  # [{player_id, gesture}]
        self._WOLF_DISCUSS_ROUNDS = 2

        # Day state
        self.current_player_idx: int = 0
        self.votes: dict[str, str] = {}
        self.vote_history: dict[int, dict[str, str]] = {}
        self.speeches: dict[int, list[dict]] = {}

        # Death tracking
        self.eliminated_order: list[str] = []
        self.night_deaths: list[str] = []     # deaths from current night
        self.pending_last_words: list[str] = []  # players who can speak last words
        self.pending_hunter_shot: bool = False
```

#### 4.4.3 关键方法实现思路

**`setup()`：**
- 解析 config 中的角色数量配置
- 随机分配角色
- 验证：`werewolf_count < total_village_count`，`total_roles == total_players`
- 初始化 wolf_ids, seer_id 等快速索引
- 进入 NIGHT_GUARD（第一个夜晚）

**`get_current_player()`：**
- 根据当前 phase 返回对应的角色玩家
- NIGHT_GUARD → guard_id（如存活）
- NIGHT_WOLF_DISCUSS → wolf_ids[wolf_discuss_idx]
- NIGHT_WOLF_KILL → wolf_ids[-1]（最后一个狼人提交决定）
- NIGHT_WITCH → witch_id
- NIGHT_SEER → seer_id
- DAY_DISCUSSION → alive_order[current_player_idx]
- DAY_VOTING → next unvoted alive player
- 如果角色已死，自动跳到下一个 phase

**`apply_action()`：** 按 action.type 分派：
- `protect` → 记录守卫目标，校验不能连续保护同一人
- `wolf_discuss` → 记录动作描述，推进讨论轮次
- `wolf_kill` → 记录击杀目标
- `witch_action` → 处理解药/毒药使用
- `seer_check` → 返回目标阵营，记录查验结果
- `speak` → 记录发言（白天讨论）
- `vote` → 记录投票，满票后结算
- `last_words` → 记录遗言
- `hunter_shoot` → 猎人开枪，目标死亡
- `skip` → 跳过（女巫不用药、猎人不开枪）

**`_resolve_night()`：** 夜晚结算逻辑
```
1. wolf_target = night_wolf_target
2. if wolf_target == guard_target → wolf_target survives (guarded)
3. if witch saved → wolf_target survives (saved)
4. if guarded AND saved → wolf_target dies (double protection = death)
5. poison_target dies unconditionally
6. Record all deaths to night_deaths
7. Check win condition
8. Transition to DAY_ANNOUNCE
```

**`_check_win_condition()`：**
```python
alive_wolves = count alive werewolves
alive_villagers = count alive non-werewolves
if alive_wolves == 0: return "village"  # village wins
if alive_wolves >= alive_villagers: return "wolf"  # wolf wins
return None  # game continues
```

**`get_private_info(player_id)`：**
- 狼人：可见所有狼人身份 + 当晚讨论内容
- 预言家：可见已查验结果
- 女巫：夜晚阶段可见被杀者 + 剩余药物
- 守卫：可见上次保护目标（防连续保护）
- 村民/猎人：无额外信息

**`get_broadcast_targets()`：**
- 狼人讨论/击杀动作 → 仅广播给狼人
- 夜晚其他角色动作 → 空列表（不广播）
- 白天发言 → 全体广播
- 投票 → 空列表（秘密投票）

**`get_agent_strategy(player_id)`：**
- 根据角色和当前 phase（夜/白天）返回对应策略

### 4.5 狼人杀 Agent 策略

**文件：** `backend/engine/werewolf/strategy.py`

提供 6 套角色策略，每套包含 thinker_prompt / evaluator_prompt / optimizer_prompt：

| 策略 | 适用角色 | 夜晚特殊约束 |
|:---|:---|:---|
| `get_werewolf_night_strategy()` | 狼人（夜晚） | 仅输出动作/手势描述 |
| `get_werewolf_day_strategy()` | 狼人（白天） | 伪装好人 |
| `get_seer_night_strategy()` | 预言家（夜晚） | 动作描述查验 |
| `get_seer_day_strategy()` | 预言家（白天） | 引导讨论 |
| `get_witch_night_strategy()` | 女巫（夜晚） | 动作描述用药 |
| `get_witch_day_strategy()` | 女巫（白天） | 信息利用 |
| `get_guard_night_strategy()` | 守卫（夜晚） | 动作描述保护 |
| `get_villager_day_strategy()` | 村民（白天） | 逻辑分析 |
| `get_hunter_day_strategy()` | 猎人（白天/死亡） | 开枪决策 |

夜晚策略 prompt 核心约束示例：
```
你现在在夜晚行动。你不能说话，只能通过肢体动作、手势、眼神来表达意图。
描述你的动作，例如："缓缓指向某个方向""做了一个否定的手势""点了点头"
绝对不能出现任何文字对话或语言描述。
```

### 4.6 游戏规则 Prompt

**文件：** `backend/engine/werewolf/prompts.py`

提供完整的狼人杀游戏规则 prompt，供 `get_game_rules_prompt()` 返回。包含：
- 角色介绍与阵营划分
- 夜晚流程（行动顺序、动作约束）
- 白天流程（讨论、投票）
- 胜负条件
- 特殊规则（守卫不连续保护、女巫限用药物、猎人开枪）

### 4.7 游戏配置文件

**文件：** `config/games/werewolf.yaml`

```yaml
# Role counts
werewolf_count: 2
villager_count: 2
seer: true
witch: true
hunter: true
guard: true

# Players (total must match role total)
players:
  - name: "张三"
    persona: "沉稳老练的退休教师"
    appearance: "花白头发，戴着老花镜"
  - name: "李四"
    persona: "活泼开朗的大学生"
    appearance: "短发，穿着卫衣"
  # ... 8 players for 2 wolves + 2 villagers + 4 special roles
```

## 5. Data Model

### 5.1 Engine Models（不变）

`backend/engine/models.py` 中的 `Action`, `ActionResult`, `GameResult`, `PlayerState` 保持不变。

WerewolfGame 复用 `PlayerState`，通过 `role` 字段区分角色（"werewolf", "villager", "seer", "witch", "hunter", "guard"）。

### 5.2 Script Schema（不变）

`backend/script/schema.py` 保持不变。狼人杀游戏通过已有的 `GameEvent.phase` 和 `Action.type` / `Action.payload` 表达所有事件。

Action type 映射：

| action.type | action.payload | 对应 phase |
|:---|:---|:---|
| `protect` | `{target: player_id}` | night_guard |
| `wolf_discuss` | `{gesture: "动作描述"}` | night_wolf_discuss |
| `wolf_kill` | `{target: player_id}` | night_wolf_kill |
| `witch_action` | `{use: "antidote"\|"poison"\|"skip", target?: player_id}` | night_witch |
| `seer_check` | `{target: player_id}` | night_seer |
| `speak` | `{content: "发言内容"}` | day_discussion |
| `vote` | `{target_player_id: player_id}` | day_voting |
| `last_words` | `{content: "遗言内容"}` | day_last_words |
| `hunter_shoot` | `{target: player_id}` 或 `{skip: true}` | day_hunter |

## 6. API Design

无新增 API。CLI 入口 (`backend/main.py`) 已支持通过 `game_type` 参数切换游戏，无需修改。

## 7. Key Flows

### 7.1 Runner 重构后的通用游戏循环

见 4.3 节伪代码。关键点：Runner 的内循环完全由 `engine.get_current_player()` 驱动，Runner 不感知具体 phase 含义。

### 7.2 狼人杀一轮完整流程

```
Night:
  [NIGHT_GUARD] guard → protect(target)
  [NIGHT_WOLF_DISCUSS] wolf1 → wolf_discuss(gesture) × 2 rounds
                       wolf2 → wolf_discuss(gesture) × 2 rounds
  [NIGHT_WOLF_KILL] last_wolf → wolf_kill(target)
  [NIGHT_WITCH] witch → witch_action(use/skip)
  [NIGHT_SEER] seer → seer_check(target)
  → _resolve_night() → check win

Day:
  [DAY_ANNOUNCE] (engine internally sets night_deaths in public_state)
  [DAY_LAST_WORDS] dead_players → last_words(content)
  [DAY_HUNTER] hunter → hunter_shoot(target/skip) (if hunter died)
  → check win
  [DAY_DISCUSSION] all alive → speak(content) in order
  [DAY_VOTING] all alive → vote(target)
  → _resolve_votes() → check win
  → next round (NIGHT_GUARD)
```

### 7.3 Phase 跳过逻辑

Engine 在 phase 转换时检查角色是否存活/可用：
- `_advance_to_next_phase()` 方法在每个 phase 结束后调用
- 如果下一个 phase 的对应角色已死亡或无可用动作，自动跳到再下一个 phase
- 例如：守卫已死 → 跳过 NIGHT_GUARD → 直接进入 NIGHT_WOLF_DISCUSS

## 8. Shared Modules & Reuse Strategy

| 共享模块 | 位置 | 使用者 |
|:---|:---|:---|
| GameEngine 基类 | `engine/base.py` | SpyGame, WerewolfGame |
| Action/ActionResult/GameResult | `engine/models.py` | 所有 engine + runner |
| PlayerState | `engine/models.py` | SpyGame, WerewolfGame |
| Registry | `engine/registry.py` | 所有 engine |
| AgentStrategy | `agent/strategy.py` | 所有 engine 的策略模块 |
| GameRecorder + Schema | `script/` | Runner (game-agnostic) |
| PlayerAgent | `agent/player.py` | Runner (game-agnostic) |
| AppSettings / PlayerConfig | `core/config.py` | Runner |
| IllegalActionError | `core/exceptions.py` | 所有 engine |

**新增共享：** GameEngine 基类的 5 个新方法提供默认实现，所有游戏开箱可用。

**无新增共享模块：** WerewolfGame 的角色逻辑和策略 prompt 高度游戏特有，不需要抽象为共享模块。

## 9. Risks & Notes

| 风险 | 影响 | 缓解措施 |
|:---|:---|:---|
| `get_agent_strategy` 签名变更破坏 SpyGame | SpyGame 编译失败 | 同步更新 SpyGame，添加 player_id 参数 |
| Runner 重构可能引入 Spy 游戏回归 bug | 现有游戏行为变化 | 运行现有 Spy 测试验证 |
| 夜晚"动作描述"约束 LLM 可能不遵守 | LLM 输出语言文字而非动作 | 策略 prompt 强调约束 + evaluator 检查 |
| 狼人讨论 2 轮可能不够形成有效策略 | 讨论质量低 | 可配置化讨论轮数，默认 2 轮 |
| DAY_ANNOUNCE phase 无玩家行动 | Runner 的 `get_current_player()` 返回 None | Engine 在进入 DAY_ANNOUNCE 时自动设置 public_state 并跳到下一个需要行动的 phase |

**关键设计决策记录：**

1. **同守同救规则：** 守卫保护 + 女巫解药同时作用于同一目标 → 目标死亡。这是简化规则，避免"救活概率"争议。
2. **行动顺序：** 守卫 → 狼人 → 女巫 → 预言家。女巫在狼人之后可以获知被杀者；预言家最后行动，查验结果反映当晚最终状态。
3. **DAY_ANNOUNCE 处理：** 不是一个需要玩家行动的 phase。Engine 在进入此 phase 时立即将 night_deaths 写入 public_state，然后自动推进到 DAY_LAST_WORDS 或 DAY_DISCUSSION。
4. **猎人开枪时机：** 仅在死亡时触发（夜晚死亡或白天投票死亡），不能主动开枪。

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
