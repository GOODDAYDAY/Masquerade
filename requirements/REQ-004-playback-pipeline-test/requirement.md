# REQ-004: Playback Pipeline Fix & End-to-End Test

**Status:** Completed
**Created:** 2026-03-15
**Priority:** High

## 1. Background

The web theater playback system (REQ-003) has a broken data pipeline. Analysis of `game_spy_20260314_232220.json` reveals that the backend `GameRunner` produces malformed script JSON:

- All events (3 rounds × 4 players = 24 events) are crammed into a single round entry
- `vote_result.votes` is empty `{}` (votes not captured)
- `phase` field on events is inconsistent (some voting events show `phase="speaking"`)
- `result.total_rounds = 3` but `rounds.length = 1`

This causes the frontend `TimelineController.buildSceneList()` to produce incorrect scene sequences, and `VotingScene` has no vote data to display.

## 2. Goals

1. **Fix backend script recording** — ensure `GameRunner` + `GameRecorder` produce correctly structured multi-round JSON
2. **Add end-to-end pipeline test** — mock game → JSON output → validate frontend-compatible structure
3. **Verify frontend playback** — each step (scene) is independent and plays correctly

## 3. Functional Requirements

### F-01: Fix GameRunner Round Recording

**Problem:** `runner.py` fails to call `recorder.start_round()` for subsequent rounds; all events end up in round 1.

**Root cause analysis:**
- After the last vote in a round, `engine.apply_action()` calls `_resolve_votes()` which increments `self.round_number` and transitions to next round's speaking phase
- The inner `while` loop in `runner.py` detects `live_round != current_round` and breaks
- But the vote_result extraction and next round's `start_round()` may not handle this transition correctly

**Fix requirements:**
- Each round in the output JSON must contain only that round's events
- Speaking events and voting events must be separated by round
- `vote_result` must contain the actual `votes` dict (who voted for whom) per round

### F-02: Fix Phase Field Recording

**Problem:** `_build_event()` reads `phase` from `engine.get_public_state()` AFTER `apply_action()`, but the engine may have already transitioned phases internally.

**Fix requirements:**
- Capture `phase` BEFORE calling `engine.apply_action()`
- Or derive phase from `action.type` (speak → "speaking", vote → "voting")

### F-03: Fix Vote Result Extraction

**Problem:** `_extract_vote_result()` returns `votes={}` despite votes being recorded in the engine.

**Fix requirements:**
- `vote_result.votes` must contain `{voter_id: target_id}` for every voter
- `vote_result.eliminated` must correctly reflect the elimination (or null for ties)

### F-04: End-to-End Pipeline Test Script

Create a test that:
1. Uses existing `MockLLMClient` to drive a complete mock game (reuse test infrastructure from `test_spy_game.py`)
2. Generates script JSON via `GameRecorder`
3. **Validates JSON structure** for frontend compatibility:
   - `rounds.length == result.total_rounds`
   - Each round has correct number of speaking events (1 per alive player)
   - Each round has correct number of voting events (1 per alive player)
   - Each round's `vote_result.votes` is non-empty
   - `phase` field matches `action.type` for all events
   - All player IDs in events exist in `players` array
4. **Validates scene conversion** (pure logic, no React):
   - Import `buildSceneList` logic (or reimplement in Python) to verify scene sequence
   - Expected scene order: opening → [round-title(speaking) → speaking×N → round-title(voting) → voting] × R → finale
   - Scene count matches expected formula

### F-05: Script Structure Validator Utility

Create a reusable validator function/script that:
- Takes a `game_spy_*.json` file path
- Validates structural correctness (schema + cross-field consistency)
- Reports all issues found
- Can be run standalone or imported by tests

## 4. Test Scenarios

### Scenario A: Civilian Wins (1 round)
- 4 players, spy eliminated in round 1
- Expected: 1 round, 4 speaking events, 4 voting events, 1 elimination
- Expected scenes: opening + round-title(speaking) + 4×speaking + round-title(voting) + 1×voting + finale = 9 scenes

### Scenario B: Spy Wins (2 rounds)
- 4 players, 2 civilians eliminated across 2 rounds
- Expected: 2 rounds, 7 speaking events (4+3), 7 voting events (4+3), 2 eliminations
- Expected scenes: opening + (rt-s + 4×sp + rt-v + vt) + (rt-s + 3×sp + rt-v + vt) + finale = 15 scenes

### Scenario C: Tie Game (3 rounds, spy wins by deadlock)
- 4 players, 3 consecutive ties, no elimination
- Expected: 3 rounds, 12 speaking events (4+4+4), 12 voting events (4+4+4), 0 eliminations
- Expected scenes: opening + 3×(rt-s + 4×sp + rt-v + vt) + finale = 23 scenes

## 5. Acceptance Criteria

- [x] AC-01: Generated JSON has `rounds.length == result.total_rounds`
- [x] AC-02: Each round contains only its own events (speaking + voting)
- [x] AC-03: `vote_result.votes` is populated for every round
- [x] AC-04: `phase` field is consistent with `action.type` for all events
- [x] AC-05: All 3 test scenarios pass structural validation
- [x] AC-06: `buildSceneList()` produces correct scene count and order for all scenarios
- [x] AC-07: Existing `test_spy_game.py` scenarios continue to pass
- [x] AC-08: Script validator can validate the existing `game_spy_20260314_232220.json` and report all issues found

## 6. Out of Scope

- Frontend React component testing (E2E/browser tests)
- Audio playback testing
- Real LLM integration testing
- UI visual regression testing

## 7. Dependencies

- REQ-002 (test infrastructure: MockLLMClient, build_speak_responses, etc.)
- REQ-003 (frontend timeline.ts buildSceneList logic)
