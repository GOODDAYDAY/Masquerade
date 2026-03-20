"""Game runner — orchestrates Engine + Agent + Recorder to drive a full game.

The runner is game-agnostic. It receives a game type name and a raw config dict.
The engine parses its own config. The runner only needs player IDs to create agents.
All game-specific logic (strategy selection, action logging, broadcast rules,
round summaries) is delegated to the engine via its interface methods.

Supports concurrent execution: when the engine returns multiple actionable players,
their LLM thinking runs in parallel (controlled by max_concurrency), while engine
state mutations (apply_action) remain strictly serial.
"""

import asyncio
from datetime import datetime

from backend.agent.models import AgentResponse
from backend.agent.player import PlayerAgent
from backend.core.config import (
    AppSettings,
    PlayerConfig,
    resolve_player_llm,
)
from backend.core.logging import get_logger
from backend.engine.base import GameEngine
from backend.engine.registry import get_game_engine
from backend.reasoning import GameReasoningGraph
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

logger = get_logger("orchestrator.runner")


class GameRunner:
    """Drives a complete game session from setup to script output."""

    def __init__(
        self,
        game_type: str,
        game_config: dict,
        app_settings: AppSettings | None = None,
    ) -> None:
        self.game_type = game_type
        self.game_config = game_config
        self.app_settings = app_settings or AppSettings()
        self.event_bus = EventBus()
        self.grg = GameReasoningGraph()

    async def run(self) -> GameScript:
        """Execute a full game and return the recorded script."""
        logger.info("Starting game: type=%s, max_concurrency=%d",
                     self.game_type, self.app_settings.max_concurrency)

        # 1. Create engine and run game setup (roles, words, etc.)
        engine, player_configs = self._setup_engine()
        # 2. Initialize graph reasoning with player personas
        self._setup_grg(player_configs)
        # 3. Create one AI agent per player
        agents = self._create_agents(player_configs)
        # 4. Create recorder for script output
        recorder = self._setup_recorder(engine, player_configs)
        # 5. Run the main game loop (rounds → actions → round-end)
        await self._run_game_loop(engine, agents, recorder)
        # 6. Record result, export script, save to disk
        script, script_path = self._finalize_game(engine, recorder)
        # 7. Generate TTS audio from script
        await self._generate_tts(script_path)

        return script

    # ═════════════════════════════════════════════
    #  Setup steps
    # ═════════════════════════════════════════════

    def _setup_engine(self) -> tuple[GameEngine, list[PlayerConfig]]:
        """Create engine, build player configs, and run engine setup."""
        engine_cls = get_game_engine(self.game_type)
        engine = engine_cls()
        player_configs = self._build_player_configs()
        self._player_configs = player_configs
        player_ids = [pc.name for pc in player_configs]
        engine.setup(player_ids, self.game_config)
        return engine, player_configs

    def _setup_grg(self, player_configs: list[PlayerConfig]) -> None:
        """Initialize graph reasoning with player personas."""
        personas = {pc.name: pc.persona for pc in player_configs}
        player_ids = [pc.name for pc in player_configs]
        self.grg.setup(player_ids, personas)

    def _create_agents(self, player_configs: list[PlayerConfig]) -> dict[str, PlayerAgent]:
        """Create one PlayerAgent per player."""
        return {pc.name: PlayerAgent(player_id=pc.name, config=pc) for pc in player_configs}

    def _setup_recorder(
        self, engine: GameEngine, player_configs: list[PlayerConfig],
    ) -> GameRecorder:
        """Create recorder with game info and player info list."""
        game_info = GameInfo(
            type=self.game_type,
            config=self.game_config,
            created_at=datetime.now(),
        )
        player_infos = self._build_player_infos(engine, player_configs)
        return GameRecorder(game_info, player_infos)

    def _build_player_infos(
        self, engine: GameEngine, player_configs: list[PlayerConfig],
    ) -> list[PlayerInfo]:
        """Build player info list in engine's shuffled order."""
        config_map = {pc.name: pc for pc in player_configs}
        player_infos = []
        for pid in engine.get_player_ids():
            pc = config_map[pid]
            role_info = engine.get_role_info(pid)
            role = role_info.pop("role", "")
            word = role_info.pop("word", "")
            player_infos.append(PlayerInfo(
                id=pid, name=pid,
                model=pc.model, persona=pc.persona, appearance=pc.appearance,
                role=role, word=word, extra=role_info,
            ))
        return player_infos

    # ═════════════════════════════════════════════
    #  Game loop
    # ═════════════════════════════════════════════

    async def _run_game_loop(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        recorder: GameRecorder,
    ) -> None:
        """Run the main game loop: rounds → batches → round-end processing."""
        self.event_bus.emit("game_start")
        max_concurrency = self.app_settings.max_concurrency
        round_count = 0

        while not engine.is_ended():
            current_round = engine.get_public_state().get("round_number", round_count + 1)
            recorder.start_round(current_round)
            self.event_bus.emit("round_start", {"round": current_round})
            round_count += 1
            logger.info("========== Round %d ==========", current_round)

            await self._run_round_actions(engine, agents, recorder, max_concurrency, current_round)
            self._process_round_end(engine, agents, recorder, current_round)

    async def _run_round_actions(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        recorder: GameRecorder,
        max_concurrency: int,
        current_round: int,
    ) -> None:
        """Process all action batches within a single round."""
        while not engine.is_ended():
            live_round = engine.get_public_state().get("round_number", current_round)
            if live_round != current_round:
                break

            batch = engine.get_actionable_players()
            if not batch:
                break

            phase = engine.get_public_state().get("phase", "")
            await self._process_batch(engine, agents, batch, phase, recorder, max_concurrency)

    def _process_round_end(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        recorder: GameRecorder,
        current_round: int,
    ) -> None:
        """Handle all round-end tasks: deaths, votes, summary, GRG update."""
        # 1. Record night deaths as system events (for frontend display)
        self._record_night_deaths(engine, recorder)
        # 2. Record vote result if engine provides one
        self._record_vote_result(engine, recorder, current_round)
        # 3. Broadcast round summary to all agents' memory
        self._broadcast_round_summary(engine, agents, current_round)
        # 4. Update graph reasoning with this round's data
        self._update_grg_round(engine, current_round)

    def _record_night_deaths(self, engine: GameEngine, recorder: GameRecorder) -> None:
        """Record night deaths as a system event for frontend display."""
        night_deaths = engine.get_public_state().get("night_deaths", [])
        if not night_deaths:
            return
        from backend.engine.models import Action as EngineAction
        death_event = GameEvent(
            player_id="system",
            phase="death_announce",
            action=EngineAction(
                type="death_announce",
                player_id="system",
                payload={"deaths": ",".join(night_deaths)},
            ),
        )
        recorder.record_event(death_event)
        logger.info("Night deaths announced: %s", ", ".join(night_deaths))

    def _record_vote_result(
        self, engine: GameEngine, recorder: GameRecorder, current_round: int,
    ) -> None:
        """Record vote result if engine provides one."""
        vote_data = engine.get_vote_result(current_round)
        if vote_data:
            recorder.record_vote_result(VoteResult(
                votes=vote_data.get("votes", {}),
                eliminated=vote_data.get("eliminated"),
            ))

    def _broadcast_round_summary(
        self, engine: GameEngine, agents: dict[str, PlayerAgent], current_round: int,
    ) -> None:
        """Broadcast round-end summary to all agents."""
        round_summary = engine.get_round_end_summary(current_round)
        if round_summary:
            logger.info(">>> Round %d summary: %s", current_round, round_summary)
            for agent in agents.values():
                agent.update_public_memory(round_summary)

    def _update_grg_round(self, engine: GameEngine, current_round: int) -> None:
        """Update graph reasoning with round data."""
        self.grg.update_round(current_round, engine.get_public_state())
        for pid in engine.get_player_ids():
            self.grg.update_private(pid, current_round, engine.get_private_info(pid))

    # ═════════════════════════════════════════════
    #  Finalization
    # ═════════════════════════════════════════════

    def _finalize_game(self, engine: GameEngine, recorder: GameRecorder) -> tuple[GameScript, str]:
        """Record game result, export and save script. Returns (script, path)."""
        result = engine.get_result()
        if result:
            recorder.set_result(GameResult(
                winner=result.winner,
                eliminated_order=result.eliminated_order,
                total_rounds=result.total_rounds,
            ))

        self.event_bus.emit("game_end", {"result": result})

        script = recorder.export()
        script_path = recorder.save(self.app_settings.scripts_dir)
        logger.info("========== Game Over ==========")
        if result:
            logger.info("Winner: %s | Rounds: %d | Eliminated: %s",
                        result.winner, result.total_rounds, ", ".join(result.eliminated_order))
        logger.info("Script saved: %s", script_path)
        return script, script_path

    # ═════════════════════════════════════════════
    #  Batch processing — parallel think, serial apply
    # ═════════════════════════════════════════════

    async def _process_batch(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        batch: list[str],
        phase: str,
        recorder: GameRecorder,
        max_concurrency: int,
    ) -> None:
        """Process a batch of players. Single = serial, multiple = concurrent."""
        if len(batch) == 1:
            await self._process_serial(engine, agents, batch[0], phase, recorder)
            return

        logger.info("[%s] Concurrent batch: %d players, max_concurrency=%d",
                     phase, len(batch), max_concurrency)

        # 1. Snapshot context for all agents BEFORE any action (fairness)
        contexts = self._snapshot_contexts(engine, batch)
        # 2. Run LLM thinking concurrently with semaphore
        results = await self._think_concurrent(agents, contexts, max_concurrency)
        # 3. Apply results serially (engine state mutation must be sequential)
        self._apply_and_record_results(engine, agents, results, contexts, phase, recorder)

    def _snapshot_contexts(
        self, engine: GameEngine, batch: list[str],
    ) -> dict[str, dict]:
        """Snapshot context for all agents BEFORE any action (fairness)."""
        alive_players = engine.get_public_state().get("alive_players", [])
        contexts: dict[str, dict] = {}
        for pid in batch:
            contexts[pid] = {
                "strategy": engine.get_agent_strategy(pid),
                "public_state": engine.get_public_state(),
                "private_info": engine.get_private_info(pid),
                "available_actions": engine.get_available_actions(pid),
                "rules_prompt": engine.get_game_rules_prompt(),
                "tools_schema": engine.get_tools_schema(),
                "grg_thinker_ctx": self.grg.get_thinker_context(pid, alive_players),
                "grg_evaluator_ctx": self.grg.get_evaluator_context(pid),
            }
        return contexts

    async def _think_concurrent(
        self,
        agents: dict[str, PlayerAgent],
        contexts: dict[str, dict],
        max_concurrency: int,
    ) -> list[tuple[str, AgentResponse | None, Exception | None]]:
        """Run LLM thinking for all players concurrently with semaphore."""
        sem = asyncio.Semaphore(max_concurrency)

        async def think_with_limit(pid: str) -> tuple[str, AgentResponse | None, Exception | None]:
            async with sem:
                ctx = contexts[pid]
                try:
                    response = await agents[pid].think_and_act(
                        game_rules_prompt=ctx["rules_prompt"],
                        public_state=ctx["public_state"],
                        private_info=ctx["private_info"],
                        available_actions=ctx["available_actions"],
                        tools_schema=ctx["tools_schema"],
                        strategy=ctx["strategy"],
                        grg_thinker_context=ctx["grg_thinker_ctx"],
                        grg_evaluator_context=ctx["grg_evaluator_ctx"],
                    )
                    return (pid, response, None)
                except Exception as e:
                    logger.exception("Concurrent think failed for %s", pid)
                    return (pid, None, e)

        return await asyncio.gather(*[think_with_limit(pid) for pid in contexts])

    def _apply_and_record_results(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        results: list[tuple[str, AgentResponse | None, Exception | None]],
        contexts: dict[str, dict],
        phase: str,
        recorder: GameRecorder,
    ) -> None:
        """Serial apply + record + broadcast for all concurrent results."""
        for pid, response, error in results:
            response = self._ensure_valid_response(agents, pid, response, error, contexts)
            self._apply_single_action(engine, agents, pid, response, phase, recorder)

    def _ensure_valid_response(
        self,
        agents: dict[str, PlayerAgent],
        pid: str,
        response: AgentResponse | None,
        error: Exception | None,
        contexts: dict[str, dict],
    ) -> AgentResponse:
        """Use fallback response if thinking failed."""
        if error is not None or response is None:
            logger.warning("Using fallback response for %s", pid)
            return agents[pid]._fallback_response(contexts[pid]["available_actions"], 0)
        return response

    def _apply_single_action(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        pid: str,
        response: AgentResponse,
        phase: str,
        recorder: GameRecorder,
    ) -> None:
        """Apply one action to engine, record, and broadcast."""
        try:
            engine.apply_action(pid, response.action)
        except Exception as e:
            logger.warning("apply_action failed for %s: %s, skipping", pid, e)
            return

        self.grg.record_action(pid, response.action.type, response.action.payload)
        logger.info(engine.format_action_log(pid, response.action))

        recorder.record_event(self._build_event(pid, response, agents[pid], phase))
        self._broadcast_action(engine, agents, pid, response.action)
        self.event_bus.emit("player_action", {
            "player_id": pid,
            "action": response.action.model_dump(),
        })

    # ═════════════════════════════════════════════
    #  Serial processing
    # ═════════════════════════════════════════════

    async def _process_serial(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        player_id: str,
        phase: str,
        recorder: GameRecorder,
    ) -> None:
        """Process a single player turn — serial think + apply."""
        available = engine.get_available_actions(player_id)
        if not available:
            return

        logger.info("[%s] %s's turn (available: %s)", phase, player_id, available)

        strategy = engine.get_agent_strategy(player_id)
        response = await self._agent_think(engine, agents[player_id], player_id, strategy)
        self._apply_single_action(engine, agents, player_id, response, phase, recorder)

    async def _agent_think(
        self, engine: GameEngine, agent: PlayerAgent, player_id: str, strategy,
    ) -> AgentResponse:
        """Execute LLM thinking only — no engine state mutation."""
        public_state = engine.get_public_state()
        alive_players = public_state.get("alive_players", [])

        return await agent.think_and_act(
            game_rules_prompt=engine.get_game_rules_prompt(),
            public_state=public_state,
            private_info=engine.get_private_info(player_id),
            available_actions=engine.get_available_actions(player_id),
            tools_schema=engine.get_tools_schema(),
            strategy=strategy,
            grg_thinker_context=self.grg.get_thinker_context(player_id, alive_players),
            grg_evaluator_context=self.grg.get_evaluator_context(player_id),
        )

    # ═════════════════════════════════════════════
    #  Helpers
    # ═════════════════════════════════════════════

    def _broadcast_action(
        self, engine: GameEngine, agents: dict[str, PlayerAgent],
        player_id: str, action,
    ) -> None:
        """Broadcast action summary to appropriate players per engine rules."""
        targets = engine.get_broadcast_targets(player_id, action)
        target_ids = list(agents.keys()) if targets is None else targets

        if not target_ids:
            return

        summary = engine.format_public_summary(player_id, action)
        for pid in target_ids:
            if pid in agents:
                agents[pid].update_public_memory(summary)

    def _build_event(
        self, player_id: str, response: AgentResponse, agent: PlayerAgent, phase: str,
    ) -> GameEvent:
        """Build a GameEvent from player response."""
        return GameEvent(
            player_id=player_id,
            phase=phase,
            thinking_duration_ms=response.thinking_duration_ms,
            thinking=response.thinking,
            expression=response.expression,
            action=response.action,
            strategy_tip=response.strategy_tip,
            memory_snapshot=MemorySnapshot(
                private=list(agent.memory.private_memory[-3:]),
                public=list(agent.memory.public_memory[-5:]),
            ),
        )

    async def _generate_tts(self, script_path: str) -> None:
        """Generate TTS audio for the game script. Skips if edge-tts not installed."""
        try:
            from backend.tts.generate import generate_audio
            logger.info("Generating TTS audio...")
            voice_config = {pc.name: pc.voice for pc in self._player_configs if pc.voice}
            manifest = await generate_audio(
                script_path, voice_config=voice_config or None,
            )
            logger.info("TTS done: %d files generated", len(manifest.get("files", [])))
        except ImportError:
            logger.info("edge-tts not installed, skipping TTS generation")
        except Exception:
            logger.exception("TTS generation failed, skipping")

    def _build_player_configs(self) -> list[PlayerConfig]:
        """Extract player configs from game config and resolve LLM defaults."""
        llm_defaults = self.app_settings.llm
        raw_players = self.game_config.get("players", [])

        if not raw_players:
            raise ValueError("Game config must include a 'players' list")

        configs = []
        for raw in raw_players:
            pc = PlayerConfig(**raw)
            configs.append(resolve_player_llm(pc, llm_defaults))
        return configs
