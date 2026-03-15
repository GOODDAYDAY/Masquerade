# REQ-004: Technical Design

**Status:** Draft
**Created:** 2026-03-15

## 1. Change Overview

Three areas of work:

| Area | Files | Nature |
|:-----|:------|:-------|
| Backend fix | `backend/orchestrator/runner.py` | Bug fix: round recording, phase capture, vote extraction |
| Frontend minor fix | `frontend/src/components/PlaybackControls.tsx`, `SpeakingScene.tsx` | Bug fix: duplicate hook call, audio timing |
| E2E test | `backend/tests/test_script_pipeline.py` | New file: script structure validation |

## 2. Backend Fix: runner.py

### 2.1 Problem Analysis

Tracing the game loop in `runner.py` lines 94-174:

```
Outer loop: while not engine.is_ended()
  recorder.start_round(current_round)       ← called once per round ✓
  Inner loop: while engine.get_current_player()
    live_round check → break if changed      ← detects round transition ✓
    agent_response = _agent_turn(...)        ← calls engine.apply_action() inside
    event = _build_event(...)                ← reads phase AFTER apply_action ✗
    recorder.record_event(event)
  vote_result = _extract_vote_result(...)    ← extracts from post-transition state ✗
```

**Bug 1 — Phase capture timing:**
`_build_event()` (line 227-238) calls `engine.get_public_state().get("phase")` AFTER `engine.apply_action()`. When the last player speaks, `apply_action` transitions phase from "speaking" → "voting". When the last player votes, it transitions to next round's "speaking" or "ended". So the recorded phase is wrong.

**Fix:** Capture `phase` BEFORE calling `_agent_turn()`.

**Bug 2 — Vote result extraction:**
`_extract_vote_result()` uses `vote_history.get(current_round, {})`. After the inner loop breaks (round transition detected), the engine's `get_public_state()` now shows the NEW round. But `current_round` still holds the old value, so `vote_history.get(current_round)` should work for the int key.

However, looking at the actual output where `votes={}`: the real issue is that `_extract_vote_result` takes `last_eliminated = eliminated[-1]` which doesn't distinguish between rounds. When round 2 has no elimination (tie), it should record the round 2 vote details but `last_eliminated` still points to round 1's elimination (or None for ties).

**Fix:** Rewrite `_extract_vote_result` to extract the current round's votes from `vote_history[current_round]` directly and determine elimination by comparing `eliminated_players` before and after the round.

**Bug 3 — Round boundary edge case:**
The outer loop re-reads `public_state.get("round_number")` at the top, which may differ from the engine's actual round when vote resolution simultaneously transitions. The inner loop's `live_round` check catches this, but the vote result recording at lines 147-150 happens after state has already transitioned.

**Fix:** Track `eliminated_players` count before the inner loop, compare after to determine if someone was eliminated in THIS round.

### 2.2 Implementation Plan

Changes to `runner.py`:

```python
# Before inner loop: snapshot eliminated count
eliminated_before = len(engine.get_public_state().get("eliminated_players", []))

# Inside inner loop, BEFORE _agent_turn:
phase_before = engine.get_public_state().get("phase", "unknown")

# Pass phase_before to _build_event instead of reading from engine after action
event = self._build_event(current_player, agent_response, agents[current_player], phase_before)

# After inner loop: extract vote result using round number and eliminated diff
public_state = engine.get_public_state()
vote_history = public_state.get("vote_history", {})
current_votes = vote_history.get(current_round, {})
eliminated_after = public_state.get("eliminated_players", [])
new_eliminated = eliminated_after[eliminated_before:] if len(eliminated_after) > eliminated_before else []
last_eliminated = new_eliminated[-1] if new_eliminated else None
vote_result = VoteResult(votes=current_votes, eliminated=last_eliminated)
```

Update `_build_event` signature:
```python
def _build_event(self, player_id, response, agent, phase: str) -> GameEvent:
    # Use passed-in phase instead of reading from engine
```

Delete `_extract_vote_result` method (logic inlined into main loop for clarity).

### 2.3 Modified runner.py — Key Changes

1. **Line ~102:** Add `eliminated_before = len(...)` before inner loop
2. **Line ~116:** Add `phase_before = engine.get_public_state().get("phase")` before `_agent_turn`
3. **Line ~130:** Pass `phase_before` to `_build_event`
4. **Line ~147-153:** Replace `_extract_vote_result` call with inline logic using `eliminated_before`/`eliminated_after` diff and `vote_history.get(current_round)`
5. **`_build_event`:** Change to accept `phase: str` parameter instead of reading from engine
6. **Delete `_extract_vote_result`:** Logic now inline

## 3. Frontend Minor Fixes

### 3.1 PlaybackControls.tsx — Duplicate useTheater

**Problem:** `useTheater()` called twice (line 22 and line 28).

**Fix:** Merge into single call, destructure `audioManager` together:
```typescript
const {
  timeline, audioManager, isPlaying, currentIndex, totalScenes, speed,
  setIsPlaying, setSpeed,
} = useTheater();
```

### 3.2 SpeakingScene.tsx — Audio timing at speed > 1x

**Problem:** `textDurationMs` divides by `speed`, but `audioDurationMs` does not. At 2x speed, text finishes in half the time but audio still plays at 1x, so `Math.max(audio, text)` always picks audio. The 800ms buffer is also not speed-adjusted.

**Fix:**
```typescript
const waitMs = Math.max(audioDurationMs, textDurationMs) + 800 / speed;
```

Note: We do NOT divide `audioDurationMs` by `speed` because the `<audio>` element plays at native speed (we don't set `playbackRate`). The fix just adjusts the buffer. If we want audio to match speed, that's a future enhancement (set `audio.playbackRate = speed`), but out of scope for REQ-004.

## 4. E2E Test: test_script_pipeline.py

### 4.1 File Location

`backend/tests/test_script_pipeline.py` — new file alongside existing `test_spy_game.py`.

### 4.2 Architecture

Reuse mock infrastructure from `test_spy_game.py`:
- `MockLLMClient`, `build_speak_responses`, `build_vote_responses`, `create_mock_agent`
- Extract these to `backend/tests/helpers.py` for sharing (or import directly)

**Decision:** Import directly from `test_spy_game.py` to avoid refactoring. These are test utilities, not production code.

### 4.3 Test Structure

```python
# backend/tests/test_script_pipeline.py

"""E2E pipeline test: mock game → JSON → structural validation.

Validates that GameRunner produces frontend-compatible script JSON.
"""

# --- Script Validator ---
def validate_script(script: GameScript) -> list[str]:
    """Validate a GameScript for structural correctness. Returns list of errors."""
    errors = []
    # 1. rounds.length == result.total_rounds
    # 2. Each round has correct event counts
    # 3. vote_result.votes is non-empty per round
    # 4. phase matches action.type
    # 5. All player_ids exist in players array
    # 6. Events in each round belong to that round's alive players
    return errors

# --- Scene Count Validator ---
def validate_scene_list(script: GameScript) -> list[str]:
    """Validate expected scene count and order."""
    # Replicate buildSceneList logic in Python
    # Check: opening + per-round(round-title-s + speaking*N + round-title-v + voting) + finale
    return errors

# --- Scenario A: Civilian Wins (1 round) ---
async def scenario_civilian_wins_pipeline() -> list[str]:
    # Same setup as test_spy_game.py scenario 1
    # Run through GameRunner (not manual loop)
    # validate_script() + validate_scene_list()

# --- Scenario B: Spy Wins (2 rounds) ---
async def scenario_spy_wins_pipeline() -> list[str]:
    # Same setup as test_spy_game.py scenario 2
    # Run through GameRunner (not manual loop)

# --- Scenario C: Tie Game (3 rounds) ---
async def scenario_tie_game_pipeline() -> list[str]:
    # New scenario: all votes are ties for 3 rounds
    # Validates the exact case from game_spy_20260314_232220.json

# --- Validate Existing JSON ---
def scenario_validate_existing_json() -> list[str]:
    # Load game_spy_20260314_232220.json
    # Run validate_script() to report known issues
    # (This scenario is expected to FAIL before backend fix, PASS after)

# --- Main ---
async def run_all() -> int:
    ...
```

### 4.4 Validation Rules

| Rule | Check | Expected |
|:-----|:------|:---------|
| V-01 | `len(rounds) == result.total_rounds` | Equal |
| V-02 | Each round: speaking events = alive player count | Match |
| V-03 | Each round: voting events = alive player count | Match |
| V-04 | Each round: `vote_result` is not None | True |
| V-05 | Each round: `vote_result.votes` is non-empty | True |
| V-06 | All events: `phase` matches `action.type` mapping | speak→speaking, vote→voting |
| V-07 | All events: `player_id` in `players` array | True |
| V-08 | Scene count formula matches | opening(1) + per_round(2 titles + speaking_N + 1 voting) + finale(1) |
| V-09 | Scene order: no speaking after voting within same round | Correct order |
| V-10 | `result.eliminated_order` matches round-by-round eliminations | Consistent |

### 4.5 Scene Count Formula

For a game with R rounds and alive player counts `[n1, n2, ..., nR]`:

```
total_scenes = 1 (opening)
             + sum over each round: 1 (round-title speaking)
                                  + ni (speaking scenes)
                                  + 1 (round-title voting)
                                  + 1 (voting scene)
             + 1 (finale)
           = 2 + sum(ni + 3 for each round)
           = 2 + 3R + sum(ni)
```

Scenario A: R=1, n=[4] → 2 + 3 + 4 = 9
Scenario B: R=2, n=[4,3] → 2 + 6 + 7 = 15
Scenario C: R=3, n=[4,4,4] → 2 + 9 + 12 = 23

### 4.6 Using GameRunner vs Manual Loop

The existing `test_spy_game.py` uses a manual `run_game()` loop that mirrors `GameRunner.run()`. For pipeline testing, we should test through `GameRunner` directly to validate the actual production code path, but we need to:

1. Inject mock LLM clients into agents created by GameRunner
2. Skip TTS generation

**Approach:** Subclass `GameRunner` to override `_agent_turn` and `_generate_tts`, or monkey-patch after construction. Simpler: just use the manual `run_game()` from `test_spy_game.py` since it mirrors the exact logic — the bugs are in runner.py's logic which we'll fix and the manual loop should replicate.

**Final decision:** Test through the actual `GameRunner.run()` by:
1. Creating `GameRunner` with test config
2. After `GameRunner.__init__`, override `_generate_tts` to no-op
3. After agents are created internally, replace their `llm_client` with mocks

This requires `GameRunner.run()` to expose a hook or we restructure slightly. Simpler alternative: refactor the manual `run_game()` in test to match the fixed runner.py logic exactly, and add a note that this mirrors `GameRunner.run()`.

**Chosen approach:** Use manual `run_game()` from test_spy_game.py (imported), since it already mirrors runner logic and doesn't need TTS/LLM infrastructure. The runner.py fix is validated by checking both test files produce correct output.

## 5. Execution Order

1. Fix `runner.py` (bugs 1-3)
2. Fix `PlaybackControls.tsx` (duplicate hook)
3. Fix `SpeakingScene.tsx` (timing buffer)
4. Create `test_script_pipeline.py` with validator + 3 scenarios
5. Run existing `test_spy_game.py` to verify no regression
6. Run new `test_script_pipeline.py` to verify all scenarios pass
7. Optionally: re-run real game to generate fresh JSON, validate with new test

## 6. Files Changed

| File | Action | Lines ~changed |
|:-----|:-------|:---------------|
| `backend/orchestrator/runner.py` | Modify | ~30 lines |
| `frontend/src/components/PlaybackControls.tsx` | Modify | ~3 lines |
| `frontend/src/components/scenes/SpeakingScene.tsx` | Modify | ~1 line |
| `backend/tests/test_script_pipeline.py` | New | ~350 lines |

## 7. Risk Assessment

| Risk | Mitigation |
|:-----|:-----------|
| runner.py fix breaks existing test | Run test_spy_game.py after fix |
| Manual test loop diverges from runner | Code comments + structural match |
| Tie game scenario mock response count | Carefully calculate: 3 rounds × (4 speak turns × 3 calls + 4 vote turns × 2 calls) = 60 calls |
