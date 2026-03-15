"""Integration test for blank role — mixed mode and all-blank mode.

Three scenarios:
  E. Blank eliminated → civilian wins
  F. Blank survives to final 2 → blank wins
  G. All-blank mode → last 2 survivors win
"""

import asyncio
import random
import sys
from datetime import datetime

from backend.core.logging import get_logger, setup_logging
from backend.engine.spy.game import SpyGame
from backend.script.recorder import GameRecorder
from backend.script.schema import (
    GameInfo,
    GameResult,
    PlayerInfo,
)

from backend.tests.test_spy_game import (
    build_speak_responses,
    build_vote_responses,
    create_mock_agent,
    run_game,
)

from backend.tests.test_script_pipeline import (
    validate_script,
    validate_scene_list,
)

_SCENARIO_TIMEOUT = 15
logger = get_logger("test_blank_game")


def _setup_game(player_ids, config, seed=42):
    engine = SpyGame()
    random.seed(seed)
    engine.setup(player_ids, config)

    roles = {}
    for pid in player_ids:
        info = engine.get_role_info(pid)
        roles[pid] = info["role"]

    return engine, roles


def _create_recorder(engine, player_ids, config):
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
# Scenario E: Blank eliminated, civilian wins
# ---------------------------------------------------------------------------

async def scenario_e_blank_eliminated() -> list[str]:
    """4 players (2C+1S+1B), blank voted out R1, spy voted out R2 → civilian wins."""
    errors = []
    player_ids = ["p1", "p2", "p3", "p4"]
    config = {"spy_count": 1, "blank_count": 1}

    engine, roles = _setup_game(player_ids, config)
    spy_id = [pid for pid, r in roles.items() if r == "spy"][0]
    blank_id = [pid for pid, r in roles.items() if r == "blank"][0]
    civilian_ids = [pid for pid, r in roles.items() if r == "civilian"]
    print("  Spy: %s, Blank: %s, Civilians: %s" % (spy_id, blank_id, civilian_ids))

    agent_responses = {pid: [] for pid in player_ids}

    # Round 1: all speak, then vote to eliminate blank
    for pid in player_ids:
        agent_responses[pid].extend(build_speak_responses("R1 speech by %s" % pid))
        if pid == blank_id:
            # Blank votes for spy (can't vote self)
            agent_responses[pid].extend(build_vote_responses(spy_id))
        else:
            agent_responses[pid].extend(build_vote_responses(blank_id))

    # Round 2: 3 survivors (2C+1S), vote out spy
    surviving_r2 = [pid for pid in player_ids if pid != blank_id]
    for pid in surviving_r2:
        agent_responses[pid].extend(build_speak_responses("R2 speech by %s" % pid))
        if pid == spy_id:
            agent_responses[pid].extend(build_vote_responses(civilian_ids[0]))
        else:
            agent_responses[pid].extend(build_vote_responses(spy_id))

    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy()
    recorder = _create_recorder(engine, player_ids, config)

    script = await run_game(engine, agents, strategy, recorder)

    errors.extend(validate_script(script))
    errors.extend(validate_scene_list(script))

    if script.result is None:
        errors.append("result is None")
    elif script.result.winner != "civilian":
        errors.append("expected winner=civilian, got %s" % script.result.winner)

    # Verify blank has role="blank" and word=""
    blank_player = next((p for p in script.players if p.id == blank_id), None)
    if blank_player:
        if blank_player.role != "blank":
            errors.append("blank player role should be 'blank', got '%s'" % blank_player.role)
        if blank_player.word != "":
            errors.append("blank player word should be empty, got '%s'" % blank_player.word)

    return errors


# ---------------------------------------------------------------------------
# Scenario F: Blank survives to final 2
# ---------------------------------------------------------------------------

async def scenario_f_blank_survives() -> list[str]:
    """4 players (2C+1S+1B), civilians eliminated → non-civilian wins."""
    errors = []
    player_ids = ["p1", "p2", "p3", "p4"]
    config = {"spy_count": 1, "blank_count": 1}

    engine, roles = _setup_game(player_ids, config, seed=42)
    spy_id = [pid for pid, r in roles.items() if r == "spy"][0]
    blank_id = [pid for pid, r in roles.items() if r == "blank"][0]
    civilian_ids = [pid for pid, r in roles.items() if r == "civilian"]
    print("  Spy: %s, Blank: %s, Civilians: %s" % (spy_id, blank_id, civilian_ids))

    target_r1 = civilian_ids[0]
    target_r2 = civilian_ids[1]

    agent_responses = {pid: [] for pid in player_ids}

    # Round 1: vote out civilian[0]
    for pid in player_ids:
        agent_responses[pid].extend(build_speak_responses("R1 speech by %s" % pid))
        if pid == target_r1:
            agent_responses[pid].extend(build_vote_responses(target_r2))
        else:
            agent_responses[pid].extend(build_vote_responses(target_r1))

    # Round 2: 3 survivors, vote out civilian[1]
    surviving_r2 = [pid for pid in player_ids if pid != target_r1]
    for pid in surviving_r2:
        agent_responses[pid].extend(build_speak_responses("R2 speech by %s" % pid))
        if pid == target_r2:
            other = [p for p in surviving_r2 if p != target_r2]
            agent_responses[pid].extend(build_vote_responses(other[0]))
        else:
            agent_responses[pid].extend(build_vote_responses(target_r2))

    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy()
    recorder = _create_recorder(engine, player_ids, config)

    script = await run_game(engine, agents, strategy, recorder)

    errors.extend(validate_script(script))
    errors.extend(validate_scene_list(script))

    if script.result is None:
        errors.append("result is None")
    else:
        # Both spy and blank survived → winner should be "spy,blank"
        winner = script.result.winner
        if "spy" not in winner or "blank" not in winner:
            errors.append("expected winner containing spy,blank, got '%s'" % winner)

    return errors


# ---------------------------------------------------------------------------
# Scenario G: All-blank mode
# ---------------------------------------------------------------------------

async def scenario_g_all_blank() -> list[str]:
    """4 players all blank (spy_count=0, blank_count=4), 2 eliminated → last 2 win."""
    errors = []
    player_ids = ["p1", "p2", "p3", "p4"]
    config = {"spy_count": 0, "blank_count": 4}

    engine, roles = _setup_game(player_ids, config)
    print("  Roles: %s" % roles)

    # Verify all are blank
    for pid, role in roles.items():
        if role != "blank":
            errors.append("player %s should be blank, got %s" % (pid, role))

    # Verify private info
    for pid in player_ids:
        pinfo = engine.get_private_info(pid)
        if not pinfo.get("is_blank"):
            errors.append("player %s private_info should have is_blank=True" % pid)

    agent_responses = {pid: [] for pid in player_ids}

    # Round 1: vote out p1 (p2,p3,p4 vote for p1; p1 votes for p2)
    for pid in player_ids:
        agent_responses[pid].extend(build_speak_responses("R1 bluff by %s" % pid))
    agent_responses["p1"].extend(build_vote_responses("p2"))
    agent_responses["p2"].extend(build_vote_responses("p1"))
    agent_responses["p3"].extend(build_vote_responses("p1"))
    agent_responses["p4"].extend(build_vote_responses("p1"))

    # Round 2: 3 survivors (p2,p3,p4), vote out p2
    for pid in ["p2", "p3", "p4"]:
        agent_responses[pid].extend(build_speak_responses("R2 bluff by %s" % pid))
    agent_responses["p2"].extend(build_vote_responses("p3"))
    agent_responses["p3"].extend(build_vote_responses("p2"))
    agent_responses["p4"].extend(build_vote_responses("p2"))

    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy()
    recorder = _create_recorder(engine, player_ids, config)

    script = await run_game(engine, agents, strategy, recorder)

    errors.extend(validate_script(script))
    errors.extend(validate_scene_list(script))

    if script.result is None:
        errors.append("result is None")
    else:
        winner = script.result.winner
        # All survivors are blank → winner should be "blank"
        if winner != "blank":
            errors.append("expected winner='blank', got '%s'" % winner)

    if len(script.rounds) != 2:
        errors.append("expected 2 rounds, got %d" % len(script.rounds))

    return errors


# ---------------------------------------------------------------------------
# Scenario H: 6-player mixed (4C+1S+1B), spy eliminated → civilian wins
# ---------------------------------------------------------------------------

async def scenario_h_six_player_mixed() -> list[str]:
    """6 players (4C+1S+1B), spy and blank both eliminated → civilian wins."""
    errors = []
    player_ids = ["p1", "p2", "p3", "p4", "p5", "p6"]
    config = {"spy_count": 1, "blank_count": 1}

    engine, roles = _setup_game(player_ids, config, seed=99)
    spy_id = [pid for pid, r in roles.items() if r == "spy"][0]
    blank_id = [pid for pid, r in roles.items() if r == "blank"][0]
    civilian_ids = [pid for pid, r in roles.items() if r == "civilian"]
    print("  Spy: %s, Blank: %s, Civilians: %s" % (spy_id, blank_id, civilian_ids))

    # Verify role counts
    role_counts = {}
    for r in roles.values():
        role_counts[r] = role_counts.get(r, 0) + 1
    if role_counts.get("spy") != 1:
        errors.append("expected 1 spy, got %s" % role_counts.get("spy"))
    if role_counts.get("blank") != 1:
        errors.append("expected 1 blank, got %s" % role_counts.get("blank"))
    if role_counts.get("civilian") != 4:
        errors.append("expected 4 civilians, got %s" % role_counts.get("civilian"))

    agent_responses = {pid: [] for pid in player_ids}

    # Round 1: all 6 speak, then vote out blank
    for pid in player_ids:
        agent_responses[pid].extend(build_speak_responses("R1 speech by %s" % pid))
        if pid == blank_id:
            agent_responses[pid].extend(build_vote_responses(spy_id))
        else:
            agent_responses[pid].extend(build_vote_responses(blank_id))

    # Round 2: 5 survivors, vote out spy
    surviving_r2 = [pid for pid in player_ids if pid != blank_id]
    for pid in surviving_r2:
        agent_responses[pid].extend(build_speak_responses("R2 speech by %s" % pid))
        if pid == spy_id:
            agent_responses[pid].extend(build_vote_responses(civilian_ids[0]))
        else:
            agent_responses[pid].extend(build_vote_responses(spy_id))

    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy()
    recorder = _create_recorder(engine, player_ids, config)

    script = await run_game(engine, agents, strategy, recorder)

    errors.extend(validate_script(script))
    errors.extend(validate_scene_list(script))

    if script.result is None:
        errors.append("result is None")
    elif script.result.winner != "civilian":
        errors.append("expected winner=civilian, got '%s'" % script.result.winner)

    if len(script.rounds) != 2:
        errors.append("expected 2 rounds, got %d" % len(script.rounds))
    if len(script.players) != 6:
        errors.append("expected 6 players, got %d" % len(script.players))

    # Round 1 should have 6 speaking + 6 voting events
    if script.rounds:
        r1_speak = len([e for e in script.rounds[0].events if e.action.type == "speak"])
        r1_vote = len([e for e in script.rounds[0].events if e.action.type == "vote"])
        if r1_speak != 6:
            errors.append("R1 expected 6 speaking events, got %d" % r1_speak)
        if r1_vote != 6:
            errors.append("R1 expected 6 voting events, got %d" % r1_vote)

    # Expected scenes: opening + (rt-s + 6sp + rt-v + vt) + (rt-s + 5sp + rt-v + vt) + finale = 19
    expected_scenes = 2 + 3 * 2 + (6 + 5)
    actual_scenes = 2 + 3 * len(script.rounds) + sum(
        len([e for e in r.events if e.action.type == "speak"]) for r in script.rounds
    )
    if actual_scenes != expected_scenes:
        errors.append("expected %d scenes, got %d" % (expected_scenes, actual_scenes))

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_all() -> int:
    setup_logging(level="INFO", log_dir="logs")

    scenarios = [
        ("Scenario E: Blank Eliminated (civilian wins, 4p)", scenario_e_blank_eliminated),
        ("Scenario F: Blank Survives (non-civilian wins, 4p)", scenario_f_blank_survives),
        ("Scenario G: All-Blank (4p, spy_count=0 blank_count=4)", scenario_g_all_blank),
        ("Scenario H: 6-Player Mixed (4C+1S+1B)", scenario_h_six_player_mixed),
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

    print("\n" + "=" * 50)
    print("Blank Game Test Results:")
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
