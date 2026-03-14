"""Integration test for Spy game — drives the full game pipeline with mock LLM.

Mirrors the exact call chain: GameRunner flow → PlayerAgent.think_and_act()
→ LangGraph (Thinker → Evaluator → Optimizer) → SpyGame engine.

Two scenarios:
  1. Civilian wins — spy eliminated in round 1
  2. Spy wins — spy survives to final 2 players

Memory safety: bounded mock responses, per-scenario timeout, no real HTTP.
"""

import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path

from backend.agent.graph import build_player_graph
from backend.agent.player import PlayerAgent
from backend.core.config import PlayerConfig
from backend.core.logging import get_logger, setup_logging
from backend.engine.models import Action
from backend.engine.spy.game import SpyGame
from backend.orchestrator.event_bus import EventBus
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

# Timeout per scenario (seconds)
_SCENARIO_TIMEOUT = 15
_SCRIPTS_DIR = "output/scripts"

logger = get_logger("test_spy_game")


# ---------------------------------------------------------------------------
# Mock LLM Client
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Queue-based mock LLM client. Each chat() call pops the next response."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._index = 0
        self._total = len(responses)

    async def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        if self._index >= self._total:
            raise RuntimeError(
                "Mock responses exhausted: consumed %d/%d" % (self._index, self._total)
            )
        resp = self._responses[self._index]
        self._index += 1
        return resp

    @property
    def calls_made(self) -> int:
        return self._index


# ---------------------------------------------------------------------------
# Mock response builders
# ---------------------------------------------------------------------------

def _thinker_speak(content: str, expression: str = "thinking") -> str:
    """Build a thinker node response for a speak action."""
    return json.dumps({
        "situation_analysis": "Mock analysis for speaking",
        "strategy": "Mock strategy: describe the word carefully",
        "action_type": "speak",
        "action_content": content,
        "expression": expression,
    }, ensure_ascii=False)


def _thinker_vote(target_id: str, expression: str = "serious") -> str:
    """Build a thinker node response for a vote action."""
    return json.dumps({
        "situation_analysis": "Mock analysis for voting",
        "strategy": "Mock strategy: vote for the most suspicious player",
        "action_type": "vote",
        "action_content": target_id,
        "expression": expression,
    }, ensure_ascii=False)


def _evaluator_pass() -> str:
    """Build an evaluator response that always passes (score >= threshold)."""
    return json.dumps({"score": 8.0, "feedback": "Good strategy"})


def _optimizer_speak(content: str, expression: str = "confident") -> str:
    """Build an optimizer response for a speak action."""
    return json.dumps({
        "optimized_content": content,
        "expression": expression,
    }, ensure_ascii=False)


def build_speak_responses(content: str) -> list[str]:
    """3 responses for a speak turn: thinker + evaluator + optimizer."""
    return [
        _thinker_speak(content),
        _evaluator_pass(),
        _optimizer_speak(content),
    ]


def build_vote_responses(target_id: str) -> list[str]:
    """2 responses for a vote turn: thinker + evaluator (optimizer skipped)."""
    return [
        _thinker_vote(target_id),
        _evaluator_pass(),
    ]


# ---------------------------------------------------------------------------
# Helper: create agents with mock LLM
# ---------------------------------------------------------------------------

def create_mock_agent(player_id: str, responses: list[str]) -> PlayerAgent:
    """Create a PlayerAgent with MockLLMClient injected."""
    config = PlayerConfig(
        name=player_id,
        model="mock-model",
        api_base="http://mock",
        api_key="mock-key",
        persona="Test player %s" % player_id,
    )
    agent = PlayerAgent(player_id=player_id, config=config)

    # Replace real LLM client and rebuild graph with mock
    mock_client = MockLLMClient(responses)
    agent.llm_client = mock_client
    agent.graph = build_player_graph(mock_client)

    return agent


# ---------------------------------------------------------------------------
# Game loop — mirrors GameRunner.run() exactly
# ---------------------------------------------------------------------------

async def run_game(
    engine: SpyGame,
    agents: dict[str, PlayerAgent],
    strategy,
    recorder: GameRecorder,
) -> GameScript:
    """Drive a full game. This replicates GameRunner.run() logic."""
    event_bus = EventBus()
    event_bus.emit("game_start")

    _action_failures = 0
    _MAX_ACTION_FAILURES = 3
    tracked_round = 0
    last_eliminated_count = 0

    while not engine.is_ended():
        public_state = engine.get_public_state()
        current_round = public_state.get("round_number", 1)

        # Detect round transition
        if current_round != tracked_round:
            # Record vote result for the previous round (if any)
            if tracked_round > 0:
                eliminated = public_state.get("eliminated_players", [])
                new_eliminated = eliminated[last_eliminated_count:] if len(eliminated) > last_eliminated_count else []
                last_elim = new_eliminated[-1] if new_eliminated else None
                recorder.record_vote_result(VoteResult(eliminated=last_elim))
                last_eliminated_count = len(eliminated)
                if last_elim:
                    print("    => %s eliminated" % last_elim)
                else:
                    print("    => No elimination (tie)")

            tracked_round = current_round
            recorder.start_round(current_round)
            event_bus.emit("round_start", {"round": current_round})
            print("  Round %d — phase: %s" % (current_round, public_state["phase"]))

        current_player = engine.get_current_player()
        if not current_player:
            break

        available = engine.get_available_actions(current_player)
        if not available:
            break

        # Agent decision — same as GameRunner._agent_turn()
        agent = agents[current_player]
        public_state = engine.get_public_state()
        private_info = engine.get_private_info(current_player)
        rules_prompt = engine.get_game_rules_prompt()
        tools_schema = engine.get_tools_schema()

        response = await agent.think_and_act(
            game_rules_prompt=rules_prompt,
            public_state=public_state,
            private_info=private_info,
            available_actions=available,
            tools_schema=tools_schema,
            strategy=strategy,
        )

        # Apply action to engine
        try:
            engine.apply_action(current_player, response.action)
            _action_failures = 0
        except Exception as e:
            _action_failures += 1
            print("    Engine rejected action from %s: %s" % (current_player, e))
            if _action_failures >= _MAX_ACTION_FAILURES:
                raise RuntimeError(
                    "Too many consecutive action failures (%d), aborting game" % _action_failures
                )
            continue

        # Record event
        event = GameEvent(
            player_id=current_player,
            phase=public_state.get("phase", "unknown"),
            thinking_duration_ms=response.thinking_duration_ms,
            thinking=response.thinking,
            expression=response.expression,
            action=response.action,
            memory_snapshot=MemorySnapshot(
                private=list(agent.memory.private_memory[-3:]),
                public=list(agent.memory.public_memory[-5:]),
            ),
        )
        recorder.record_event(event)

        # Broadcast public info
        summary = _format_public_summary(current_player, response.action)
        for a in agents.values():
            a.update_public_memory(summary)

        # Print action
        if response.action.type == "speak":
            print("    %s speaks: %s" % (current_player, response.action.payload.get("content", "")))
        elif response.action.type == "vote":
            print("    %s votes for: %s" % (current_player, response.action.payload.get("target_player_id", "")))

    # Record vote result for the final round
    if tracked_round > 0:
        public_state = engine.get_public_state()
        eliminated = public_state.get("eliminated_players", [])
        new_eliminated = eliminated[last_eliminated_count:] if len(eliminated) > last_eliminated_count else []
        last_elim = new_eliminated[-1] if new_eliminated else None
        recorder.record_vote_result(VoteResult(eliminated=last_elim))
        if last_elim:
            print("    => %s eliminated" % last_elim)
        elif engine.is_ended():
            pass  # Game ended, no need to print tie
        else:
            print("    => No elimination (tie)")

    # Game end
    result = engine.get_result()
    if result:
        recorder.set_result(GameResult(
            winner=result.winner,
            eliminated_order=result.eliminated_order,
            total_rounds=result.total_rounds,
        ))

    script = recorder.export()
    script_path = recorder.save(_SCRIPTS_DIR)
    print("  Script saved: %s" % script_path)

    return script


def _format_public_summary(player_id: str, action: Action) -> str:
    if action.type == "speak":
        return "%s said: %s" % (player_id, action.payload.get("content", ""))
    if action.type == "vote":
        return "%s voted for %s" % (player_id, action.payload.get("target_player_id", ""))
    return "%s did %s" % (player_id, action.type)


# ---------------------------------------------------------------------------
# Scenario 1: Civilian Wins
# ---------------------------------------------------------------------------

async def scenario_civilian_wins() -> list[str]:
    """4 players, 1 spy. Spy is eliminated in round 1. Civilian wins."""
    errors = []
    player_ids = ["player_1", "player_2", "player_3", "player_4"]

    # Setup engine
    engine = SpyGame()
    config = {"spy_count": 1, }
    random.seed(42)
    engine.setup(player_ids, config)

    # Detect who is the spy
    spy_id = None
    for pid in player_ids:
        info = engine.get_role_info(pid)
        if info["role"] == "spy":
            spy_id = pid
            break
    print("  Spy is: %s" % spy_id)

    # Build mock responses: everyone speaks, then everyone votes for spy
    speech_contents = {
        "player_1": "这个东西圆圆的，平时经常吃到。",
        "player_2": "酸酸甜甜的，很多人都喜欢。",
        "player_3": "我觉得这个东西很常见，颜色鲜艳。",
        "player_4": "可以榨汁喝，味道很清爽。",
    }

    # Build civilian list for the spy's vote target (spy can't vote for self)
    civilian_ids = [pid for pid in player_ids if pid != spy_id]

    agent_responses: dict[str, list[str]] = {}
    for pid in player_ids:
        responses = []
        # Speak turn: thinker + evaluator + optimizer = 3 calls
        responses.extend(build_speak_responses(speech_contents[pid]))
        # Vote turn: thinker + evaluator = 2 calls
        if pid == spy_id:
            # Spy votes for a civilian (can't vote for self)
            responses.extend(build_vote_responses(civilian_ids[0]))
        else:
            # Civilians vote for the spy
            responses.extend(build_vote_responses(spy_id))
        agent_responses[pid] = responses

    # Create agents with mock
    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy()

    # Create recorder
    game_info = GameInfo(type="spy", config=config, created_at=datetime.now())
    player_infos = []
    for pid in player_ids:
        role_info = engine.get_role_info(pid)
        player_infos.append(PlayerInfo(
            id=pid, name=pid, model="mock-model",
            persona="Test player", role=role_info["role"], word=role_info["word"],
        ))
    recorder = GameRecorder(game_info, player_infos)

    # Run game
    script = await run_game(engine, agents, strategy, recorder)

    # Verify results
    if not engine.is_ended():
        errors.append("Game should have ended")
    result = engine.get_result()
    if result is None:
        errors.append("Result should not be None")
    elif result.winner != "civilian":
        errors.append("Expected winner=civilian, got %s" % result.winner)
    elif spy_id not in result.eliminated_order:
        errors.append("Spy %s should be in eliminated_order" % spy_id)
    elif result.total_rounds != 1:
        errors.append("Expected 1 round, got %d" % result.total_rounds)

    # Verify script
    if script.result is None:
        errors.append("Script result should not be None")
    elif script.result.winner != "civilian":
        errors.append("Script winner should be civilian")
    if len(script.rounds) != 1:
        errors.append("Script should have 1 round, got %d" % len(script.rounds))
    if len(script.players) != 4:
        errors.append("Script should have 4 players, got %d" % len(script.players))

    # Verify script JSON file exists
    script_files = list(Path(_SCRIPTS_DIR).glob("game_spy_*.json"))
    if not script_files:
        errors.append("No script JSON file found in %s" % _SCRIPTS_DIR)
    else:
        latest = max(script_files, key=lambda p: p.stat().st_mtime)
        if latest.stat().st_size == 0:
            errors.append("Script JSON file is empty")
        else:
            # Verify deserializable
            with open(latest, "r", encoding="utf-8") as f:
                data = json.load(f)
            parsed = GameScript(**data)
            if parsed.result is None or parsed.result.winner != "civilian":
                errors.append("Deserialized script has wrong result")

    return errors


# ---------------------------------------------------------------------------
# Scenario 2: Spy Wins
# ---------------------------------------------------------------------------

async def scenario_spy_wins() -> list[str]:
    """4 players, 1 spy. Civilians are eliminated over 2 rounds. Spy wins."""
    errors = []
    player_ids = ["player_1", "player_2", "player_3", "player_4"]

    # Setup engine
    engine = SpyGame()
    config = {"spy_count": 1, }
    random.seed(42)
    engine.setup(player_ids, config)

    # Detect spy and civilians
    spy_id = None
    civilian_ids = []
    for pid in player_ids:
        info = engine.get_role_info(pid)
        if info["role"] == "spy":
            spy_id = pid
        else:
            civilian_ids.append(pid)
    print("  Spy is: %s" % spy_id)
    print("  Civilians: %s" % civilian_ids)

    # Plan: eliminate civilian_ids[0] in round 1, civilian_ids[1] in round 2
    # This leaves spy + civilian_ids[2] → spy wins (2 alive, spy survives)
    target_r1 = civilian_ids[0]
    target_r2 = civilian_ids[1]

    speech_contents_r1 = {
        "player_1": "这个东西很常见，生活中经常用到。",
        "player_2": "它有特定的形状，大家应该都认识。",
        "player_3": "我觉得它跟日常生活密切相关。",
        "player_4": "颜色和大小可以不同，但用途差不多。",
    }

    speech_contents_r2 = {
        "player_1": "补充一下，这个东西有时候是甜的。",
        "player_2": "对，而且不同品种味道也不一样。",
        "player_3": "我同意，确实是这样的。",
        "player_4": "它在超市里很容易买到。",
    }

    # Build mock responses per player across rounds
    agent_responses: dict[str, list[str]] = {pid: [] for pid in player_ids}

    # Round 1: everyone speaks then votes for target_r1
    for pid in player_ids:
        agent_responses[pid].extend(build_speak_responses(speech_contents_r1[pid]))
        if pid == target_r1:
            # Can't vote for self — vote for target_r2 instead (still a civilian)
            agent_responses[pid].extend(build_vote_responses(target_r2))
        else:
            agent_responses[pid].extend(build_vote_responses(target_r1))

    # Round 2: only surviving players (everyone except target_r1)
    surviving_r2 = [pid for pid in player_ids if pid != target_r1]
    for pid in surviving_r2:
        agent_responses[pid].extend(build_speak_responses(speech_contents_r2[pid]))
        if pid == target_r2:
            # Can't vote for self — vote for another civilian
            other_civilian = [c for c in civilian_ids if c != target_r2 and c != target_r1]
            agent_responses[pid].extend(build_vote_responses(other_civilian[0] if other_civilian else spy_id))
        else:
            agent_responses[pid].extend(build_vote_responses(target_r2))

    # Create agents
    agents = {pid: create_mock_agent(pid, agent_responses[pid]) for pid in player_ids}
    strategy = engine.get_agent_strategy()

    # Create recorder
    game_info = GameInfo(type="spy", config=config, created_at=datetime.now())
    player_infos = []
    for pid in player_ids:
        role_info = engine.get_role_info(pid)
        player_infos.append(PlayerInfo(
            id=pid, name=pid, model="mock-model",
            persona="Test player", role=role_info["role"], word=role_info["word"],
        ))
    recorder = GameRecorder(game_info, player_infos)

    # Run game
    script = await run_game(engine, agents, strategy, recorder)

    # Verify results
    if not engine.is_ended():
        errors.append("Game should have ended")
    result = engine.get_result()
    if result is None:
        errors.append("Result should not be None")
    elif result.winner != "spy":
        errors.append("Expected winner=spy, got %s" % result.winner)
    elif result.eliminated_order != [target_r1, target_r2]:
        errors.append(
            "Expected eliminated_order=%s, got %s"
            % ([target_r1, target_r2], result.eliminated_order)
        )
    elif result.total_rounds != 2:
        errors.append("Expected 2 rounds, got %d" % result.total_rounds)

    # Verify script
    if script.result is None:
        errors.append("Script result should not be None")
    elif script.result.winner != "spy":
        errors.append("Script winner should be spy")
    if len(script.rounds) != 2:
        errors.append("Script should have 2 rounds, got %d" % len(script.rounds))

    # Verify script JSON
    script_files = list(Path(_SCRIPTS_DIR).glob("game_spy_*.json"))
    if not script_files:
        errors.append("No script JSON file found")
    else:
        latest = max(script_files, key=lambda p: p.stat().st_mtime)
        if latest.stat().st_size == 0:
            errors.append("Script JSON file is empty")

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_all() -> int:
    """Run all scenarios and return exit code (0=pass, 1=fail)."""
    setup_logging(level="INFO", log_dir="logs")

    scenarios = [
        ("Scenario 1: Civilian Wins (spy eliminated round 1)", scenario_civilian_wins),
        ("Scenario 2: Spy Wins (survives to final 2)", scenario_spy_wins),
    ]

    results: list[tuple[str, bool, list[str]]] = []

    for name, func in scenarios:
        print("\n=== %s ===" % name)
        try:
            errors = await asyncio.wait_for(func(), timeout=_SCENARIO_TIMEOUT)
            passed = len(errors) == 0
            results.append((name, passed, errors))
        except asyncio.TimeoutError:
            results.append((name, False, ["TIMEOUT after %ds" % _SCENARIO_TIMEOUT]))
        except Exception as e:
            results.append((name, False, ["EXCEPTION: %s" % e]))

    # Summary
    print("\n" + "=" * 50)
    print("Test Results:")
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
