# REQ-014 Technical Design

> Status: Completed
> Requirement: requirement.md
> Created: 2026-03-16
> Updated: 2026-03-16

## 1. Technology Stack

| Module | Technology | Rationale |
|:---|:---|:---|
| Prompt templates | Python string constants | Existing pattern in `prompts.py` / `strategy.py`, no new deps |
| Game config | YAML | Existing `config/games/*.yaml` pattern |
| Shared prompt fragments | Python constants in new `backend/engine/shared_prompts.py` | DRY — anti-bias and voting rules reused across all games |

## 2. Design Principles

- **Prompt-only changes**: No LangGraph architecture, node logic, or agent framework modifications
- **DRY shared fragments**: Universal rules (anti-name-bias, voting evidence) extracted to one file, imported by all games
- **Backward compatible**: Output JSON format unchanged; existing tests must still pass
- **Persona as data, not code**: Persona enrichment is config-only (YAML), no Python changes needed for it

## 3. Architecture Overview

No architectural changes. All modifications are content-level (prompt text + YAML config).

```
Files Modified:
  backend/engine/shared_prompts.py    ← NEW: shared prompt fragments
  backend/engine/spy/prompts.py       ← REWRITE: thinker/evaluator/optimizer
  backend/engine/spy/strategy.py      ← UPDATE: inject shared fragments
  backend/engine/werewolf/prompts.py  ← REWRITE: all role prompts
  backend/engine/werewolf/strategy.py ← UPDATE: inject shared fragments
  config/games/spy.yaml               ← UPDATE: enriched personas
  config/games/werewolf.yaml          ← UPDATE: enriched personas
```

## 4. Module Design

### 4.1 Shared Prompt Fragments (`backend/engine/shared_prompts.py`)

- **Responsibility**: Single source of truth for universal prompt rules used across all games.
- **Public interface**:
  ```python
  ANTI_NAME_BIAS: str          # FR-1 constraint text
  VOTING_EVIDENCE_RULES: str   # FR-5 voting rules text
  NIGHT_SILENT_RULES: str      # FR-3.1 silent action constraint
  ```
- **Internal structure**: Pure string constants, no functions.
- **Reuse notes**: Imported by `spy/prompts.py`, `spy/strategy.py`, `werewolf/prompts.py`, `werewolf/strategy.py`. Any future game imports from here.

### 4.2 Spy Prompts Rewrite (`backend/engine/spy/prompts.py`)

- **Responsibility**: All prompt templates for spy game (thinker, evaluator, optimizer for standard/blank roles).
- **Changes**:

  | Prompt | Change Summary |
  |--------|---------------|
  | `SPY_THINKER_PROMPT` | Add multi-hypothesis reasoning, evidence-chain voting, adaptive description, round-progressive analysis. Inject `ANTI_NAME_BIAS` + `VOTING_EVIDENCE_RULES`. |
  | `SPY_EVALUATOR_PROMPT` | Add name-bias penalty (-3), evidence-based voting check (-3), multi-round awareness check (-2). Inject `ANTI_NAME_BIAS`. |
  | `SPY_OPTIMIZER_PROMPT` | Add substance requirement, voting justification must cite evidence. |
  | `BLANK_THINKER_PROMPT` | Same enhancements as spy thinker, plus blank-specific constraints. |
  | `BLANK_EVALUATOR_PROMPT` | Same new scoring criteria as spy evaluator. |
  | `BLANK_OPTIMIZER_PROMPT` | Same enhancements as spy optimizer. |

- **Pattern**: Each prompt includes shared fragments via f-string or concatenation:
  ```python
  from backend.engine.shared_prompts import ANTI_NAME_BIAS, VOTING_EVIDENCE_RULES

  SPY_THINKER_PROMPT = f"""
  ...existing game-specific content...

  {ANTI_NAME_BIAS}

  {VOTING_EVIDENCE_RULES}
  """
  ```

### 4.3 Spy Strategy Update (`backend/engine/spy/strategy.py`)

- **Responsibility**: Build `AgentStrategy` objects with the updated prompts.
- **Changes**: Minimal — just re-imports updated prompt constants. No logic changes.

### 4.4 Werewolf Prompts Rewrite (`backend/engine/werewolf/prompts.py`)

- **Responsibility**: All role-specific prompt templates for werewolf game.
- **Changes**:

  | Role | Phase | Change Summary |
  |------|-------|---------------|
  | Werewolf | Night thinker | Add `NIGHT_SILENT_RULES`, teammate communication protocol, guard-prediction depth, witch-awareness |
  | Werewolf | Night evaluator | Add silent-action check (0 if sound), inject `ANTI_NAME_BIAS` |
  | Werewolf | Night optimizer | Add silent action polish rules |
  | Werewolf | Day thinker | Inject `ANTI_NAME_BIAS` + `VOTING_EVIDENCE_RULES`, deeper disguise strategy |
  | Werewolf | Day evaluator | Add name-bias penalty, evidence check |
  | Seer | Day thinker | Clearer jump timing, counter-seer protocol, gold-chain presentation |
  | Seer | Night thinker | Inject `ANTI_NAME_BIAS` for verification target selection |
  | Witch | Night thinker | Stronger poison encouragement, first-night save guidance, info synthesis |
  | Witch | Night evaluator | Penalize skipping when should poison |
  | Guard | Night thinker | Multi-level meta-game, exposed-role priority, self-protect |
  | Villager | Day thinker | Active deduction framework, speech analysis guide, team consolidation. Inject `ANTI_NAME_BIAS` + `VOTING_EVIDENCE_RULES` |
  | Hunter | Death thinker | Shoot priority, anti-skip emphasis |
  | Hunter | Death evaluator | Penalize skipping |

### 4.5 Werewolf Strategy Update (`backend/engine/werewolf/strategy.py`)

- **Responsibility**: Build role-specific `AgentStrategy` objects.
- **Changes**: Re-imports updated prompt constants. No logic changes.

### 4.6 Spy Persona Config (`config/games/spy.yaml`)

- **Responsibility**: Player definitions for spy game.
- **Changes**: Expand each player's `persona` from 1 line to 4 dimensions:
  1. 性格特点 (personality traits)
  2. 说话风格 (speech patterns)
  3. 决策方式 (decision style)
  4. 弱点 (weakness)

  3 players × 4 dimensions = ~12 lines of new persona content.

### 4.7 Werewolf Persona Config (`config/games/werewolf.yaml`)

- **Responsibility**: Player definitions for werewolf game.
- **Changes**: Same 4-dimension expansion for all 12 players. ~48 lines of new persona content.

## 5. Data Model

No data model changes. `AgentStrategy` interface unchanged:
```python
class AgentStrategy(BaseModel):
    thinker_prompt: str
    evaluator_prompt: str
    optimizer_prompt: str
    evaluation_threshold: float = 6.0
    max_retries: int = 2
```

## 6. API Design

No API changes.

## 7. Key Flows

No flow changes. The existing LangGraph pipeline (Thinker → Evaluator → Optimizer) is unchanged. Only the prompt content injected into each node changes.

```
[Unchanged] Agent receives AgentStrategy with new prompt text
[Unchanged] Thinker uses strategy.thinker_prompt → LLM call → JSON response
[Unchanged] Evaluator uses strategy.evaluator_prompt → LLM scoring
[Unchanged] Optimizer uses strategy.optimizer_prompt → LLM polish
```

The **behavioral change** comes entirely from what the prompts ask the LLM to do, not from any code logic change.

## 8. Shared Modules & Reuse Strategy

| Module | Used By | Sharing Method |
|:---|:---|:---|
| `shared_prompts.ANTI_NAME_BIAS` | spy/prompts.py, werewolf/prompts.py | Python import, string concatenation into thinker + evaluator prompts |
| `shared_prompts.VOTING_EVIDENCE_RULES` | spy/prompts.py, werewolf/prompts.py | Python import, concatenated into thinker prompts for voting phases |
| `shared_prompts.NIGHT_SILENT_RULES` | werewolf/prompts.py | Python import, concatenated into all night-phase thinker + evaluator prompts |

## 9. Risks & Notes

| Risk | Mitigation |
|:---|:---|
| Longer prompts → slower LLM response | Acceptable tradeoff. Prompts grow ~30-50%, still within context limits. Monitor token usage. |
| Richer prompts → LLM may struggle to follow all instructions | Evaluator retries (max 2) catch format failures. Shared fragments are concise and clear. |
| Persona changes may affect voice consistency | Optimizer prompt explicitly maintains persona voice. Test with 3 games per AC. |
| Silent constraint too strict → wolf night actions become boring | Optimizer polishes gestures to be vivid (eye contact, deliberate pointing, subtle nods). Not just "points at X". |

## 10. Change Log

| Version | Date | Changes | Affected Scope | Reason |
|:---|:---|:---|:---|:---|
| v1 | 2026-03-16 | Initial version | ALL | - |
