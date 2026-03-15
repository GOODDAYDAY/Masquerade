"""E2E pipeline test: mock game -> JSON -> structural validation.

Validates that the game pipeline produces frontend-compatible script JSON.
Three scenarios + existing JSON validation.
"""

import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path

from backend.agent.player import PlayerAgent
from backend.core.logging import get_logger, setup_logging
from backend.engine.spy.game import SpyGame
from backend.script.recorder import GameRecorder
from backend.script.schema import (
    GameEvent,
    GameInfo,
    GameResult,
    GameScript,
    MemorySnapshot,
    PlayerInfo,
    VoteResult,
)

from backend.tests.test_spy_game import (
    MockLLMClient,
    build_speak_responses,
    build_vote_responses,
    create_mock_agent,
    run_game,
)

_SCENARIO_TIMEOUT = 15
_SCRIPTS_DIR = "output/scripts"

logger = get_logger("test_script_pipeline")


# ---------------------------------------------------------------------------
# Script Validator
# ---------------------------------------------------------------------------

def validate_script(script: GameScript) -> list[str]:
    """Validate a GameScript for structural correctness. Returns list of errors."""
    errors = []
    player_ids = {p.id for p in script.players}

    # V-01: rounds count matches result
    if script.result:
        if len(script.rounds) != script.result.total_rounds:
            errors.append(
                "V-01: rounds count %d != result.total_rounds %d"
                % (len(script.rounds), script.result.total_rounds)
            )

    # Track alive players across rounds
    alive = set(player_ids)

    for r in script.rounds:
        rn = r.round_number

        speaking_events = [e for e in r.events if e.action.type == "speak"]
        voting_events = [e for e in r.events if e.action.type == "vote"]

        # V-02: speaking events = alive player count
        if len(speaking_events) != len(alive):
            errors.append(
                "V-02: round %d speaking events %d != alive players %d"
                % (rn, len(speaking_events), len(alive))
            )

        # V-03: voting events = alive player count
        if len(voting_events) != len(alive):
            errors.append(
                "V-03: round %d voting events %d != alive players %d"
                % (rn, len(voting_events), len(alive))
            )

        # V-04: vote_result exists
        if r.vote_result is None:
            errors.append("V-04: round %d vote_result is None" % rn)
        else:
            # V-05: vote_result.votes is non-empty
            if not r.vote_result.votes:
                errors.append("V-05: round %d vote_result.votes is empty" % rn)

            # Update alive set based on elimination
            if r.vote_result.eliminated:
                alive.discard(r.vote_result.eliminated)

        # V-06: phase matches action.type
        phase_map = {"speak": "speaking", "vote": "voting"}
        for e in r.events:
            expected_phase = phase_map.get(e.action.type)
            if expected_phase and e.phase != expected_phase:
                errors.append(
                    "V-06: round %d event %s action=%s but phase=%s (expected %s)"
                    % (rn, e.player_id, e.action.type, e.phase, expected_phase)
                )

        # V-07: all player_ids exist in players array
        for e in r.events:
            if e.player_id not in player_ids:
                errors.append(
                    "V-07: round %d event player_id=%s not in players"
                    % (rn, e.player_id)
                )

        # V-09: speaking events come before voting events
        saw_vote = False
        for e in r.events:
            if e.action.type == "vote":
                saw_vote = True
            elif e.action.type == "speak" and saw_vote:
                errors.append(
                    "V-09: round %d speaking event after voting event (player=%s)"
                    % (rn, e.player_id)
                )

    # V-10: eliminated_order consistency
    if script.result:
        round_eliminations = []
        for r in script.rounds:
            if r.vote_result and r.vote_result.eliminated:
                round_eliminations.append(r.vote_result.eliminated)
        if round_eliminations != script.result.eliminated_order:
            errors.append(
                "V-10: round-by-round eliminations %s != result.eliminated_order %s"
                % (round_eliminations, script.result.eliminated_order)
            )

    return errors


def validate_scene_list(script: GameScript) -> list[str]:
    """Validate expected scene count from buildSceneList logic."""
    errors = []

    # Replicate buildSceneList logic in Python
    scenes = []
    scenes.append("opening")

    for r in script.rounds:
        speaking_events = [e for e in r.events if e.action.type == "speak"]
        voting_events = [e for e in r.events if e.action.type == "vote"]

        if speaking_events:
            scenes.append("round-title-speaking")
            for _ in speaking_events:
                scenes.append("speaking")

        if r.vote_result:
            scenes.append("round-title-voting")
            scenes.append("voting")

    if script.result:
        scenes.append("finale")

    # V-08: verify scene count matches formula
    # Formula: 2 + 3R + sum(speaking_per_round)
    num_rounds = len(script.rounds)
    total_speaking = sum(
        len([e for e in r.events if e.action.type == "speak"])
        for r in script.rounds
    )
    expected = 2 + 3 * num_rounds + total_speaking
    actual = len(scenes)

    if actual != expected:
        errors.append(
            "V-08: scene count %d != expected %d (formula: 2 + 3*%d + %d)"
            % (actual, expected, num_rounds, total_speaking)
        )

    return errors


# ---------------------------------------------------------------------------
# Game runner helper (mirrors test_spy_game.run_game)
# ---------------------------------------------------------------------------

def _setup_game(player_ids: list[str], seed: int = 42) -> tuple[SpyGame, dict, str, list[str]]:
    """Setup game engine and return (engine, role_map, spy_id, civilian_ids)."""
    engine = SpyGame()
    config = {"spy_count": 1}
    random.seed(seed)
    engine.setup(player_ids, config)

    spy_id = None
    civilian_ids = []
    for pid in player_ids:
        info = engine.get_role_info(pid)
        if info["role"] == "spy":
            spy_id = pid
        else:
            civilian_ids.append(pid)

    return engine, config, spy_id, civilian_ids


def _create_recorder(engine: SpyGame, player_ids: list[str], config: dict) -> GameRecorder:
    """Create a GameRecorder with player info from engine."""
    game_info = GameInfo(type="spy", config=config, created_at=datetime.now())
    player_infos = []
    for pid in player_ids:
        role_info = engine.get_role_info(pid)
        player_infos.append(PlayerInfo(
            id=pid, name=pid, model="mock-model",
            persona="Test player", role=role_info["role"], word=role_info["word"],
        ))
    return GameRecorder(game_info, player_infos)


# ---------------------------------------------------------------------------
# Scenario A: Civilian Wins (1 round, spy eliminated)
# ---------------------------------------------------------------------------

async def scenario_a_civilian_wins() -> list[str]:
    """1 round: spy eliminated, civilian wins."""
    errors = []
    player_ids = ["p1", "p2", "p3", "p4"]

    engine, config, spy_id, civilian_ids = _setup_game(player_ids)
    print("  Spy: %s" % spy_id)

    speeches = {"p1": "圆的东西", "p2": "酸甜的", "p3": "很常见", "p4": "可以榨汁"}

    agent_responses = {}
    for pid in player_ids:
        responses = build_speak_responses(speeches[pid])
        if pid == spy_id:
            responses += build_vote_responses(civilian_ids[0])
        else:
            responses += build_vote_responses(spy_id)
        agent_responses[pid] = responses

    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy(player_ids[0])
    recorder = _create_recorder(engine, player_ids, config)

    script = await run_game(engine, agents, strategy, recorder)

    # Structural validation
    errors.extend(validate_script(script))
    errors.extend(validate_scene_list(script))

    # Scenario-specific checks
    if script.result is None:
        errors.append("result is None")
    elif script.result.winner != "civilian":
        errors.append("expected winner=civilian, got %s" % script.result.winner)

    if len(script.rounds) != 1:
        errors.append("expected 1 round, got %d" % len(script.rounds))

    # Expected scenes: opening + round-title-s + 4*speaking + round-title-v + voting + finale = 9
    expected_scenes = 9
    actual_scenes = 2 + 3 * len(script.rounds) + sum(
        len([e for e in r.events if e.action.type == "speak"]) for r in script.rounds
    )
    if actual_scenes != expected_scenes:
        errors.append("expected %d scenes, got %d" % (expected_scenes, actual_scenes))

    return errors


# ---------------------------------------------------------------------------
# Scenario B: Spy Wins (2 rounds, civilians eliminated)
# ---------------------------------------------------------------------------

async def scenario_b_spy_wins() -> list[str]:
    """2 rounds: 2 civilians eliminated, spy wins."""
    errors = []
    player_ids = ["p1", "p2", "p3", "p4"]

    engine, config, spy_id, civilian_ids = _setup_game(player_ids)
    print("  Spy: %s, Civilians: %s" % (spy_id, civilian_ids))

    target_r1 = civilian_ids[0]
    target_r2 = civilian_ids[1]

    agent_responses = {pid: [] for pid in player_ids}

    # Round 1: all speak, then vote to eliminate target_r1
    for pid in player_ids:
        agent_responses[pid].extend(build_speak_responses("Round 1 speech by %s" % pid))
        if pid == target_r1:
            agent_responses[pid].extend(build_vote_responses(target_r2))
        else:
            agent_responses[pid].extend(build_vote_responses(target_r1))

    # Round 2: surviving players (all except target_r1)
    surviving = [pid for pid in player_ids if pid != target_r1]
    for pid in surviving:
        agent_responses[pid].extend(build_speak_responses("Round 2 speech by %s" % pid))
        if pid == target_r2:
            other = [c for c in civilian_ids if c != target_r2 and c != target_r1]
            agent_responses[pid].extend(build_vote_responses(other[0] if other else spy_id))
        else:
            agent_responses[pid].extend(build_vote_responses(target_r2))

    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy(player_ids[0])
    recorder = _create_recorder(engine, player_ids, config)

    script = await run_game(engine, agents, strategy, recorder)

    errors.extend(validate_script(script))
    errors.extend(validate_scene_list(script))

    if script.result is None:
        errors.append("result is None")
    elif script.result.winner != "spy":
        errors.append("expected winner=spy, got %s" % script.result.winner)

    if len(script.rounds) != 2:
        errors.append("expected 2 rounds, got %d" % len(script.rounds))

    # Expected scenes: opening + (rt-s + 4*sp + rt-v + vt) + (rt-s + 3*sp + rt-v + vt) + finale
    # = 1 + 7 + 6 + 1 = 15
    expected_scenes = 15
    actual_scenes = 2 + 3 * len(script.rounds) + sum(
        len([e for e in r.events if e.action.type == "speak"]) for r in script.rounds
    )
    if actual_scenes != expected_scenes:
        errors.append("expected %d scenes, got %d" % (expected_scenes, actual_scenes))

    return errors


# ---------------------------------------------------------------------------
# Scenario C: Tie Game (3 consecutive ties, spy wins by deadlock)
# ---------------------------------------------------------------------------

async def scenario_c_tie_game() -> list[str]:
    """3 rounds of ties, no elimination, spy wins by deadlock."""
    errors = []
    player_ids = ["p1", "p2", "p3", "p4"]

    engine, config, spy_id, civilian_ids = _setup_game(player_ids)
    print("  Spy: %s, Civilians: %s" % (spy_id, civilian_ids))

    # For a tie each round, we need 2 players voting one way and 2 the other.
    # Split: spy + civilian[0] vote for civilian[1], civilian[1] + civilian[2] vote for spy
    # Result: civilian[1] gets 2 votes, spy gets 2 votes → tie
    group_a = [spy_id, civilian_ids[0]]  # vote for civilian_ids[1]
    group_b = [civilian_ids[1], civilian_ids[2]]  # vote for spy_id

    agent_responses = {pid: [] for pid in player_ids}

    for round_num in range(1, 4):
        # All 4 players speak
        for pid in player_ids:
            agent_responses[pid].extend(
                build_speak_responses("Round %d speech by %s" % (round_num, pid))
            )
        # Voting: engineered tie
        for pid in player_ids:
            if pid in group_a:
                agent_responses[pid].extend(build_vote_responses(civilian_ids[1]))
            else:
                agent_responses[pid].extend(build_vote_responses(spy_id))

    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy(player_ids[0])
    recorder = _create_recorder(engine, player_ids, config)

    script = await run_game(engine, agents, strategy, recorder)

    errors.extend(validate_script(script))
    errors.extend(validate_scene_list(script))

    if script.result is None:
        errors.append("result is None")
    elif script.result.winner != "spy":
        errors.append("expected winner=spy, got %s" % script.result.winner)

    if len(script.rounds) != 3:
        errors.append("expected 3 rounds, got %d" % len(script.rounds))

    # No one should be eliminated
    if script.result and script.result.eliminated_order:
        errors.append("expected no eliminations, got %s" % script.result.eliminated_order)

    # All vote_results should have eliminated=None
    for r in script.rounds:
        if r.vote_result and r.vote_result.eliminated is not None:
            errors.append("round %d should have no elimination" % r.round_number)

    # Expected scenes: opening + 3*(rt-s + 4*sp + rt-v + vt) + finale
    # = 1 + 3*7 + 1 = 23
    expected_scenes = 23
    actual_scenes = 2 + 3 * len(script.rounds) + sum(
        len([e for e in r.events if e.action.type == "speak"]) for r in script.rounds
    )
    if actual_scenes != expected_scenes:
        errors.append("expected %d scenes, got %d" % (expected_scenes, actual_scenes))

    return errors


# ---------------------------------------------------------------------------
# Scenario D: Validate existing JSON
# ---------------------------------------------------------------------------

def scenario_d_validate_existing() -> list[str]:
    """Validate the existing game_spy_20260314_232220.json (expected to have known issues)."""
    errors = []
    json_path = Path(_SCRIPTS_DIR) / "game_spy_20260314_232220.json"

    if not json_path.exists():
        return ["File not found: %s" % json_path]

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    script = GameScript(**data)

    issues = validate_script(script)
    scene_issues = validate_scene_list(script)

    # This is informational — we expect issues in the old file
    if issues or scene_issues:
        print("  Known issues found in existing JSON (expected):")
        for issue in issues + scene_issues:
            print("    - %s" % issue)
        # Don't add to errors — this scenario reports but doesn't fail
    else:
        print("  No issues found (file may have been regenerated after fix)")

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_all() -> int:
    """Run all scenarios and return exit code."""
    setup_logging(level="INFO", log_dir="logs")

    scenarios = [
        ("Scenario A: Civilian Wins (1 round)", scenario_a_civilian_wins),
        ("Scenario B: Spy Wins (2 rounds)", scenario_b_spy_wins),
        ("Scenario C: Tie Game (3 consecutive ties)", scenario_c_tie_game),
    ]

    results: list[tuple[str, bool, list[str]]] = []

    for name, func in scenarios:
        print("\n=== %s ===" % name)
        try:
            errs = await asyncio.wait_for(func(), timeout=_SCENARIO_TIMEOUT)
            passed = len(errs) == 0
            results.append((name, passed, errs))
        except asyncio.TimeoutError:
            results.append((name, False, ["TIMEOUT after %ds" % _SCENARIO_TIMEOUT]))
        except Exception as e:
            results.append((name, False, ["EXCEPTION: %s" % e]))

    # Scenario D: existing JSON validation (sync, informational)
    print("\n=== Scenario D: Validate Existing JSON ===")
    try:
        d_errors = scenario_d_validate_existing()
        results.append(("Scenario D: Validate Existing JSON", len(d_errors) == 0, d_errors))
    except Exception as e:
        results.append(("Scenario D: Validate Existing JSON", False, ["EXCEPTION: %s" % e]))

    # Summary
    print("\n" + "=" * 50)
    print("Pipeline Test Results:")
    total = len(results)
    passed = sum(1 for _, p, _ in results if p)

    for name, ok, errs in results:
        if ok:
            print("  [PASS] %s" % name)
        else:
            print("  [FAIL] %s" % name)
            for err in errs:
                print("         - %s" % err)

    print("\n%d/%d scenarios passed" % (passed, total))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_all()))
