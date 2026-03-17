# REQ-015 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-17
> Updated: 2026-03-17

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Optimizer context fix | Python (optimizer.py) | Code-level fix: inject missing game state |
| Evaluator hint fix | Python (evaluator.py) | Code-level fix: detect wolf_discuss as content action |
| Prompt refinements | Python string constants | Content-level: gesture constraints, witch logic |
| Shared fragments | Python (shared_prompts.py) | DRY: NIGHT_GESTURE_STYLE reused by wolf prompts |

## 2. Root Cause Analysis

### Thinker vs Optimizer Context Gap

The core bug is an **information asymmetry** between the thinker and optimizer nodes.

| Context | Thinker | Optimizer |
|:---|:---|:---|
| game_rules_prompt | ✅ system message | ❌ missing |
| memory_context (all prior thinking) | ✅ injected as messages | ❌ missing |
| public_state (full game state JSON) | ✅ in prompt template | ❌ **only alive_players extracted** |
| private_info (role, word, checks) | ✅ in prompt template | ❌ missing |
| available_actions | ✅ in prompt template | ❌ missing |
| round_number | ✅ inside public_state | ❌ missing |
| speeches (who said what, all rounds) | ✅ inside public_state | ❌ **missing — causes hallucination** |
| vote_history (who voted whom) | ✅ inside public_state | ❌ missing |
| situation_analysis | self-generated | ✅ text summary only |
| action_content | self-generated | ✅ |
| persona | ✅ in system message | ✅ in prompt |

**The optimizer is essentially blind to game facts.** It receives only:
1. persona (character voice)
2. situation_analysis (thinker's analysis summary)
3. action_content (raw text to polish)
4. action_type
5. alive player names (appended)

It does NOT know: what round it is, who has spoken, what they said, what the voting history is, what role the player has. The thinker's situation_analysis is a compressed summary that may not mention all speakers or may use ambiguous references.

### Consequence: Hallucination

When the optimizer polishes speech, it tries to make it sound like a real player discussing a game. To do this naturally, it adds references to other players' statements. But since it doesn't know what was actually said, it **fabricates** these references.

Example from game log:
- Thinker (correct): "目前尚未听到任何人发言，无法评估其他人"
- Optimizer (hallucinated): "我注意到甄逻辑的发言有矛盾" ← nobody spoke yet

### Secondary Issues

**wolf_discuss skipped by evaluator/optimizer:** Both `_SPEECH_DESC_HINTS` (evaluator) and `_OPTIMIZE_DESC_HINTS` (optimizer) only match "发言/内容/说/看法/推理/遗言". The wolf_discuss tool schema describes its field as "动作描述", which doesn't match. Result: wolf gestures get no LLM quality check or polishing.

**Optimizer temperature too high:** 0.9 encourages creative/divergent output, which amplifies hallucination.

## 3. Module Design

### 3.1 Node Base Context Builder (`backend/agent/nodes/base.py`) — NEW

**Problem:** Three nodes (thinker/evaluator/optimizer) each independently build LLM messages. Thinker does it right (full context), evaluator and optimizer miss critical pieces. Copy-paste fixes are fragile.

**Fix:** Extract a shared context builder that ALL nodes use:

```python
def build_node_messages(
    state: AgentState,
    user_prompt: str,
    *,
    include_memory: bool = True,
    include_public_state: bool = True,
    include_private_info: bool = True,
) -> list[dict]:
    """Build LLM messages with full game context.

    All nodes get game_rules as system message.
    Optional: memory_context, public_state, private_info appended to user_prompt.
    Individual nodes control what they need via flags.
    """
```

Each node calls `build_node_messages(state, my_prompt, ...)` instead of manually building messages. This guarantees consistent context.

| Node | include_memory | include_public_state | include_private_info |
|:---|:---|:---|:---|
| Thinker | ✅ | ❌ (in prompt template) | ❌ (in prompt template) |
| Evaluator | ✅ | ✅ | ❌ (in prompt template) |
| Optimizer | ✅ | ✅ | ✅ |

All three nodes receive full context via `build_node_messages`. The `False` flags only avoid **duplication** where the prompt template already embeds the data via `{public_state}` or `{private_info}` placeholders.

### 3.2 Optimizer Refactor (`backend/agent/nodes/optimizer.py`)

**Problem:** Optimizer only receives persona + situation_analysis summary + action_content. It has no game rules, no memory, no public_state, no private_info. It cannot distinguish facts from fabrication.

**Fix — inject full game context into optimizer prompt:**
1. `public_state` — full JSON (round number, speeches, vote_history, alive_players, night_deaths)
2. `private_info` — role, identity info (so optimizer knows if player is wolf/seer/etc and stays in character)
3. `game_rules_prompt` — injected as system message (same as thinker)
4. `memory_context` — injected as prior messages (same as thinker)
5. Anti-hallucination constraint appended: "only reference events that appear in public_state"
6. Lower temperature from 0.9 → 0.7
7. Add "动作/手势" to `_OPTIMIZE_DESC_HINTS` so wolf_discuss gets LLM polishing

**Design:** Optimizer gets the same message structure as thinker (system + memory + user prompt), so it has identical factual grounding. The difference is the user prompt: thinker asks "analyze and decide", optimizer asks "polish this content while staying factual."

### 3.2 Evaluator Context Injection (`backend/agent/nodes/evaluator.py`)

**Problem:** Evaluator only receives situation_analysis + strategy + action_payload + private_info. No public_state, no game rules, no memory. It cannot verify if speech references real events.

**Fix — inject game context into evaluator prompt:**
1. `public_state` — full JSON appended to evaluator prompt
2. `game_rules_prompt` — injected as system message
3. Add "动作/手势" to `_SPEECH_DESC_HINTS` so wolf_discuss goes through LLM evaluation
4. This enables the evaluator to check: "did the player reference something that actually happened?"

### 3.3 Shared Prompt Fragment (`backend/engine/shared_prompts.py`)

**Changes:**
1. Add `NIGHT_GESTURE_STYLE` constant: gesture brevity rules + ban on "表示/意味着" narration

### 3.4 Wolf Night Optimizer (`backend/engine/werewolf/strategy.py`)

**Changes:**
1. Inject `NIGHT_GESTURE_STYLE` into wolf night optimizer prompt
2. Shorten gesture requirement: "1-2 actions, not 3-4 sentence templates"

### 3.5 Witch Night Thinker (`backend/engine/werewolf/strategy.py`)

**Changes:**
1. Remove "第一晚强烈建议使用解药" → replace with case-by-case analysis framework
2. Evaluator: "第一晚不救需要理由" → "无脑救也扣分，需要分析"

## 4. Risks & Notes

| Risk | Mitigation |
|:---|:---|
| Longer optimizer prompt (added context) → slower | Acceptable: only adds ~100 tokens of speech context. Total prompt still small. |
| Optimizer may ignore anti-hallucination constraint | Temperature 0.7 (down from 0.9) reduces creative divergence. Factual context gives it real quotes to reference instead of fabricating. |
| wolf_discuss LLM evaluation adds latency | Acceptable: one extra LLM call per wolf gesture. Night phase is serial anyway. |

## 5. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-17 | Initial version | ALL | - |
