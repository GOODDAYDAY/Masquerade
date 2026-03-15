# REQ-005 Technical Design

> Status: Technical Finalized
> Requirement: requirement.md
> Created: 2026-03-15
> Updated: 2026-03-15

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Game Engine | Python, Pydantic | 现有引擎扩展，无新依赖 |
| Agent Strategy | Prompt template (Jinja-style format strings) | 复用现有 AgentStrategy 框架 |
| Frontend | React, TypeScript, Framer Motion | 复用现有组件 |
| Test | asyncio, MockLLMClient | 复用 REQ-002/004 测试基础设施 |

## 2. Design Principles

- **向后兼容优先**：所有新增字段有默认值，不配置时行为不变
- **最小改动面**：在现有 `SpyGame` 类上扩展，不拆分新引擎类
- **Prompt 策略分离**：白板 prompt 与标准 prompt 共存于 `strategy.py`，通过模式选择
- **复合 winner 统一格式**：所有 winner 值统一为逗号分隔字符串，前端统一解析

## 3. Architecture Overview

改动集中在 3 层：

```
backend/engine/spy/
├── game.py          ← setup() 角色分配 + _check_win_condition() + get_private_info()
├── prompts.py       ← 动态规则文本（标准/白板/全白板）
├── strategy.py      ← 新增白板 thinker/evaluator/optimizer prompt
└── words.py         (不改)

backend/script/
└── schema.py        (不改，role/winner 已是 str 类型)

frontend/src/
├── components/
│   ├── Theater.tsx          ← 词条栏适配
│   ├── shared/PlayerAvatar.tsx  ← 白板徽章
│   └── scenes/FinaleScene.tsx   ← winner 文案
└── types/game-script.ts    (不改，类型已兼容)

config/games/
├── spy.yaml           (可选加 blank_count)
└── spy_all_blank.yaml (新增)

backend/tests/
└── test_blank_game.py (新增)
```

## 4. Module Design

### 4.1 Game Engine — SpyGame.setup() (F-01)

**Responsibility:** 根据 `mode` 和 `blank_count` 分配角色

**Changes to `setup()`:**

```python
def setup(self, players: list[str], config: dict) -> None:
    self.mode = config.get("mode", "standard")  # 新增实例变量
    self.blank_count = config.get("blank_count", 0)

    if self.mode == "all_blank":
        # 全白板模式：所有人 role=blank, word=""
        self.word_pair = ("", "")
        self.player_order = list(players)
        for pid in players:
            self.players[pid] = PlayerState(
                player_id=pid, alive=True, role="blank", word=""
            )
        # 跳过 spy_count / word_pair 逻辑
    else:
        # 标准模式（现有逻辑 + blank 扩展）
        # 验证：spy_count + blank_count < len(players)
        total_special = self.spy_count + self.blank_count
        if total_special >= len(players):
            raise IllegalActionError(...)

        # 随机选 spy_count 个卧底 + blank_count 个白板，其余平民
        indices = random.sample(range(len(players)), total_special)
        spy_indices = set(indices[:self.spy_count])
        blank_indices = set(indices[self.spy_count:])

        for i, pid in enumerate(players):
            if i in spy_indices:
                role, word = "spy", spy_word
            elif i in blank_indices:
                role, word = "blank", ""
            else:
                role, word = "civilian", civilian_word
            self.players[pid] = PlayerState(...)
```

**New instance variables:**
- `self.mode: str` — `"standard"` or `"all_blank"`
- `self.blank_count: int` — number of blank players (standard mode only)

### 4.2 Game Engine — Win Condition (F-02)

**Responsibility:** `_check_win_condition()` 和 `get_result()` 扩展

**`_check_win_condition()` 新逻辑：**

```python
def _check_win_condition(self) -> bool:
    alive = [pid for pid in self.player_order if self.players[pid].alive]

    if self.mode == "all_blank":
        # 全白板：剩2人即结束
        return len(alive) <= 2 or self.consecutive_ties >= self._MAX_CONSECUTIVE_TIES

    # 标准/混合模式
    alive_spies = [pid for pid in alive if self.players[pid].role == "spy"]
    alive_blanks = [pid for pid in alive if self.players[pid].role == "blank"]

    # 所有非平民都被淘汰 → 平民胜
    if not alive_spies and not alive_blanks:
        return True
    # 剩2人 → 非平民阵营胜
    if len(alive) <= 2:
        return True
    # 连续平票
    if self.consecutive_ties >= self._MAX_CONSECUTIVE_TIES:
        return True
    return False
```

**`get_result()` 新逻辑：**

```python
def get_result(self) -> GameResult | None:
    alive = [pid for pid in self.player_order if self.players[pid].alive]

    if self.mode == "all_blank":
        # 全白板：存活者 ID 逗号拼接
        winner = ",".join(alive)
    else:
        alive_spies = [pid for pid in alive if self.players[pid].role == "spy"]
        alive_blanks = [pid for pid in alive if self.players[pid].role == "blank"]

        if not alive_spies and not alive_blanks:
            winner = "civilian"
        else:
            # 存活的非平民角色拼接
            winners = []
            if alive_spies:
                winners.append("spy")
            if alive_blanks:
                winners.append("blank")
            winner = ",".join(winners)

    return GameResult(winner=winner, ...)
```

### 4.3 Game Engine — Private Info (F-03)

**Changes to `get_private_info()`:**

```python
def get_private_info(self, player_id: str) -> dict:
    ps = self.players.get(player_id)
    if not ps:
        return {}
    if ps.role == "blank":
        return {"word": "", "is_blank": True}
    return {"word": ps.word}
```

### 4.4 Prompts — Dynamic Rules (F-05)

**Responsibility:** `prompts.py` 改为提供多个规则模板

**Changes to `prompts.py`:**

```python
RULES_STANDARD = """...(现有 RULES_PROMPT 内容)..."""

RULES_STANDARD_WITH_BLANK = """你正在参加一场「谁是卧底」桌游。

## 游戏规则
1. 每位玩家会收到一个词语。大多数玩家（平民）拿到相同的词，少数玩家（卧底）拿到一个相近但不同的词。
   还有可能存在「白板」玩家——白板没有拿到任何词语。
2. 你不知道自己是平民、卧底还是白板...
...（含白板规则的完整版本）
"""

RULES_ALL_BLANK = """你正在参加一场「全员白板」桌游。

## 游戏规则
1. 所有玩家都没有拿到词语。
2. 每个人都不知道其他人是否有词。你需要假装自己有词并进行描述。
3. 通过观察其他人的描述，推理和伪装，尽量不被投票淘汰。
...
## 胜负条件
- 最后存活的2名玩家获胜。
"""

def get_rules_prompt(mode: str, has_blank: bool) -> str:
    if mode == "all_blank":
        return RULES_ALL_BLANK
    if has_blank:
        return RULES_STANDARD_WITH_BLANK
    return RULES_STANDARD
```

**Changes to `game.py`:**

```python
def get_game_rules_prompt(self) -> str:
    has_blank = self.blank_count > 0
    return get_rules_prompt(self.mode, has_blank)
```

### 4.5 Agent Strategy — Blank Prompt (F-04)

**Responsibility:** `strategy.py` 新增白板专用 prompt 模板

**Design:** 新增 `get_blank_strategy()` 和 `get_all_blank_strategy()` 工厂函数

```python
BLANK_THINKER_PROMPT = """你是「谁是卧底」游戏中的玩家 **{player_id}**。
你是白板——你没有拿到任何词语。

你的目标是：
1. 通过其他玩家的描述，猜测平民词和卧底词分别可能是什么
2. 伪装成拥有词语的玩家，给出合理的描述
3. 绝对不能暴露自己没有词

...（分析输出格式同标准版）
"""

ALL_BLANK_THINKER_PROMPT = """你是「全员白板」游戏中的玩家 **{player_id}**。
你没有拿到任何词语。其他人可能有词也可能没有。

你的目标是：
1. 观察其他玩家的描述，尝试推测是否有人真的有词
2. 给出含糊但合理的描述，不被投票淘汰
3. 投票淘汰你认为描述最可疑的人

...
"""
```

**Selection logic in `game.py`:**

```python
def get_agent_strategy(self) -> AgentStrategy:
    if self.mode == "all_blank":
        return get_all_blank_strategy()
    return get_spy_strategy()  # 标准版（含白板 thinker 变体在 runner 中按角色选择）
```

**Key design decision:** 在混合模式中，白板玩家需要用不同的 thinker prompt。当前 `AgentStrategy` 是整局统一的。两种方案：

- **方案 A：每个 agent 独立 strategy**——runner 在创建 agent 时根据角色注入不同 strategy
- **方案 B：strategy 包含多个 thinker prompt**——由 thinker 节点根据 `private_info.is_blank` 选择

**选择方案 A**：更简洁。在 `runner.py` 中，为白板 agent 注入 `get_blank_strategy()`。`get_agent_strategy()` 返回默认策略（给平民/卧底用），白板单独覆盖。

**Changes to `runner.py`:**

```python
# In run(), after creating agents:
strategy = engine.get_agent_strategy()
blank_strategy = get_blank_strategy() if engine.blank_count > 0 else None

# In _agent_turn(), select strategy by role:
role = engine.get_role_info(player_id).get("role", "")
active_strategy = blank_strategy if role == "blank" and blank_strategy else strategy
```

但注意：runner 不应该依赖 `get_role_info()` 做运行时决策（那是 god-view）。更好的方式是看 `get_private_info()` 中的 `is_blank` 标记：

```python
private_info = engine.get_private_info(player_id)
active_strategy = blank_strategy if private_info.get("is_blank") else strategy
```

### 4.6 Configuration (F-06)

**New file: `config/games/spy_all_blank.yaml`**

```yaml
mode: all_blank
players:
  - name: "王磊"
    persona: "谨慎保守，善于观察"
    appearance: "28岁，灰色卫衣，黑框眼镜"
  - name: "林小雨"
    persona: "活泼直接，喜欢试探别人"
    appearance: "24岁，白色T恤，马尾辫"
  - name: "张大海"
    persona: "沉稳冷静，话不多但每句都有分量"
    appearance: "35岁，深蓝衬衫，短发"
  - name: "陈思"
    persona: "心思细腻，善于察言观色"
    appearance: "26岁，淡粉色外套，长发"
```

### 4.7 Frontend — Theater Word Bar (F-08)

**Changes to `Theater.tsx` (lines 96-117):**

```typescript
// Determine display mode
const isAllBlank = script.players.every(p => p.role === "blank");
const hasBlank = script.players.some(p => p.role === "blank");
const civilianWord = script.players.find(p => p.role === "civilian")?.word ?? "";
const spyWord = script.players.find(p => p.role === "spy")?.word ?? "";

// In JSX:
{isAllBlank ? (
  <span className="text-gray-400">全员白板模式（无词）</span>
) : (
  <>
    <div>平民词 <span>{civilianWord}</span></div>
    <span>|</span>
    <div>卧底词 <span>{spyWord}</span></div>
    {hasBlank && (
      <>
        <span>|</span>
        <div>白板：<span className="text-gray-400">无词</span></div>
      </>
    )}
  </>
)}
```

### 4.8 Frontend — PlayerAvatar Badge (F-09)

**Changes to `PlayerAvatar.tsx`:**

```typescript
const isSpy = role === "spy";
const isBlank = role === "blank";

// Role badge (line 62-66):
{isSpy && !dimmed && (
  <span className="... bg-theater-danger ...">卧底</span>
)}
{isBlank && !dimmed && (
  <span className="... bg-gray-500 ...">白板</span>
)}

// Word label (line 73-76):
{!dimmed && (
  <span className={`... ${isSpy ? "bg-theater-danger/15 ..." : isBlank ? "bg-gray-500/15 text-gray-400" : "bg-theater-accent/15 ..."}`}>
    {word || "无词"}
  </span>
)}
```

### 4.9 Frontend — FinaleScene Winner (F-10)

**Changes to `FinaleScene.tsx`:**

```typescript
// Replace simple isCivilianWin logic:
function getWinnerDisplay(winner: string, players: PlayerInfo[]): { text: string; colorClass: string } {
  if (winner === "civilian") return { text: "平民阵营获胜", colorClass: "text-theater-accent" };
  if (winner === "spy") return { text: "卧底获胜", colorClass: "text-theater-danger" };
  if (winner === "blank") return { text: "白板获胜", colorClass: "text-gray-300" };
  if (winner === "spy,blank") return { text: "非平民阵营获胜", colorClass: "text-theater-danger" };
  // All-blank mode: winner is comma-separated player IDs
  const winnerIds = winner.split(",");
  const names = winnerIds.map(id => players.find(p => p.id === id)?.name ?? id);
  return { text: `存活者获胜：${names.join("、")}`, colorClass: "text-gray-300" };
}

// Winner animation: pulse for both spy and blank roles
animate={
  (p.role === "spy" || p.role === "blank")
    ? { scale: [1, 1.12, 1], transition: { repeat: 2, duration: 0.4 } }
    : {}
}
```

### 4.10 Test (F-11)

**New file: `backend/tests/test_blank_game.py`**

3 scenarios using existing mock infrastructure:

| Scenario | Setup | Expected Winner |
|:---------|:------|:----------------|
| E: Blank eliminated (civilian wins) | 4 players: 2C+1S+1B, blank voted out R1, spy voted out R2 | `"civilian"` |
| F: Blank survives (blank wins) | 4 players: 2C+1S+1B, civilians voted out | `"blank"` or `"spy,blank"` |
| G: All-blank mode | 4 players all blank, 2 eliminated | `"p1,p3"` (survivors) |

Each scenario also runs `validate_script()` + `validate_scene_list()` from `test_script_pipeline.py`.

**Updates to `test_script_pipeline.py`:**
- `validate_script()` already accepts any string for `role` and `winner` (no enum check)
- No changes needed to validator — it validates structure, not role values

## 5. Data Model

No schema changes needed. Existing types are flexible:

| Field | Type | Current Values | New Values |
|:------|:-----|:---------------|:-----------|
| `PlayerState.role` | `str` | `"civilian"`, `"spy"` | + `"blank"` |
| `PlayerState.word` | `str` | non-empty | `""` for blank |
| `GameResult.winner` | `str` | `"civilian"`, `"spy"` | + `"blank"`, `"spy,blank"`, `"id1,id2"` |
| `PlayerInfo.role` | `str` | same | same |

`schema.py`, `models.py`, `game-script.ts` — no structural changes needed. All `role` and `winner` fields are already `str` type.

## 6. API Design

No new API endpoints. Changes are internal to the game engine.

## 7. Key Flows

### 7.1 Standard + Blank Mode — Role Assignment

```
config: {spy_count: 1, blank_count: 1, players: [A,B,C,D]}
          │
          ▼
SpyGame.setup()
  ├─ total_special = 1 + 1 = 2
  ├─ Validate: 2 < 4 ✓
  ├─ Random sample 2 indices from [0,1,2,3]
  │   e.g. [1, 3]
  ├─ Index 1 → spy (word=spy_word)
  ├─ Index 3 → blank (word="")
  ├─ Index 0,2 → civilian (word=civilian_word)
  └─ Start round 1
```

### 7.2 Win Condition Decision Tree

```
_check_win_condition()
  │
  ├─ mode == "all_blank"?
  │   ├─ alive <= 2 → END (winner = survivors)
  │   └─ consecutive_ties >= 3 → END (winner = survivors)
  │
  └─ mode == "standard"
      ├─ alive spies == 0 AND alive blanks == 0 → END (winner = civilian)
      ├─ alive <= 2 → END (winner = alive non-civilian roles)
      └─ consecutive_ties >= 3 → END (winner = alive non-civilian roles)
```

### 7.3 Strategy Selection in Runner

```
GameRunner.run()
  │
  ├─ strategy = engine.get_agent_strategy()      # default (for civilian/spy)
  ├─ blank_strategy = get_blank_strategy()        # if has blank
  │
  └─ Per turn:
      private_info = engine.get_private_info(player_id)
      active_strategy = blank_strategy if private_info.get("is_blank") else strategy
      response = agent.think_and_act(..., strategy=active_strategy)
```

## 8. Shared Modules & Reuse Strategy

| Shared Component | Used By | Notes |
|:----------------|:--------|:------|
| `MockLLMClient`, `build_speak_responses`, `build_vote_responses` | test_blank_game.py | Import from test_spy_game.py |
| `validate_script()`, `validate_scene_list()` | test_blank_game.py | Import from test_script_pipeline.py |
| `run_game()` | test_blank_game.py | Import from test_spy_game.py |
| `PlayerAvatar` badge pattern | F-09 | Extend existing badge logic |
| `getWinnerDisplay()` | FinaleScene.tsx | New helper, could be reused by future game types |

## 9. Risks & Notes

| Risk | Mitigation |
|:-----|:-----------|
| 白板 prompt 质量不佳导致 agent 直接说"我没有词" | Prompt 中明确禁止暴露白板身份；evaluator 对此类发言判 0 分 |
| `runner.py` 使用 `private_info.is_blank` 选 strategy 增加了 runner 对引擎的耦合 | 可接受——runner 只读 private_info 公共接口，不直接访问引擎内部状态 |
| 全白板模式 winner 是玩家 ID 拼接，前端解析可能出错 | `getWinnerDisplay()` 做 fallback 处理，找不到名字时显示 ID |
| 现有测试回归 | blank_count 默认 0，mode 默认 standard，不影响现有路径 |

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-15 | Initial version | ALL | - |
