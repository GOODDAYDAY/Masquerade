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
        # TODO(haotian): 2026/3/16 启用
        self.event_bus = EventBus()

    async def run(self) -> GameScript:
        """Execute a full game and return the recorded script."""
        logger.info("Starting game: type=%s, max_concurrency=%d",
                     self.game_type, self.app_settings.max_concurrency)

        # 1. Create and setup engine — engine parses its own config
        engine_cls = get_game_engine(self.game_type)
        engine = engine_cls()

        player_configs = self._build_player_configs()
        self._player_configs = player_configs  # Store for TTS voice mapping
        player_ids = [pc.name for pc in player_configs]
        engine.setup(player_ids, self.game_config)

        # 2. Create agents
        agents: dict[str, PlayerAgent] = {}
        for pc in player_configs:
            agents[pc.name] = PlayerAgent(player_id=pc.name, config=pc)

        # 3. Create recorder
        game_info = GameInfo(
            type=self.game_type,
            config=self.game_config,
            created_at=datetime.now(),
        )
        # Build player_infos in engine's player_order (shuffled), not config order
        config_map = {pc.name: pc for pc in player_configs}
        player_infos = []
        for pid in engine.get_player_ids():
            pc = config_map[pid]
            role_info = engine.get_role_info(pid)
            # Extract standard fields, remaining go to extra
            role = role_info.pop("role", "")
            word = role_info.pop("word", "")
            player_infos.append(PlayerInfo(
                id=pid,
                name=pid,
                model=pc.model,
                persona=pc.persona,
                appearance=pc.appearance,
                role=role,
                word=word,
                extra=role_info,  # Game-specific fields (e.g. faction for werewolf)
            ))
        recorder = GameRecorder(game_info, player_infos)

        max_concurrency = self.app_settings.max_concurrency

        # 4. Game loop — engine-driven with batch concurrency support
        self.event_bus.emit("game_start")
        round_count = 0

        while not engine.is_ended():
            public_state = engine.get_public_state()
            current_round = public_state.get("round_number", round_count + 1)
            recorder.start_round(current_round)
            self.event_bus.emit("round_start", {"round": current_round})
            round_count += 1
            logger.info("========== Round %d ==========", current_round)

            while not engine.is_ended():
                # Break out when engine advances to the next round
                live_round = engine.get_public_state().get("round_number", current_round)
                if live_round != current_round:
                    break

                batch = engine.get_actionable_players()
                if not batch:
                    break  # No more actions this round

                phase = engine.get_public_state().get("phase", "")

                await self._process_batch(
                    engine, agents, batch, phase, recorder, max_concurrency,
                )

            # Record night deaths as a system event (for frontend display)
            public_state = engine.get_public_state()
            night_deaths = public_state.get("night_deaths", [])
            if night_deaths:
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

            # Round-end: record vote result if engine provides one
            vote_data = engine.get_vote_result(current_round)
            if vote_data:
                recorder.record_vote_result(VoteResult(
                    votes=vote_data.get("votes", {}),
                    eliminated=vote_data.get("eliminated"),
                ))

            # Round-end: broadcast summary from engine
            round_summary = engine.get_round_end_summary(current_round)
            if round_summary:
                logger.info(">>> Round %d summary: %s", current_round, round_summary)
                for agent in agents.values():
                    agent.update_public_memory(round_summary)

        # 5. Game end
        result = engine.get_result()
        if result:
            recorder.set_result(GameResult(
                winner=result.winner,
                eliminated_order=result.eliminated_order,
                total_rounds=result.total_rounds,
            ))

        self.event_bus.emit("game_end", {"result": result})

        # 6. Save and return
        script = recorder.export()
        script_path = recorder.save(self.app_settings.scripts_dir)
        logger.info("========== Game Over ==========")
        if result:
            logger.info("Winner: %s | Rounds: %d | Eliminated: %s",
                        result.winner, result.total_rounds, ", ".join(result.eliminated_order))
        logger.info("Script saved: %s", script_path)

        # 7. Generate TTS audio
        await self._generate_tts(script_path)

        return script

    # =========================================================================
    # Batch processing — parallel think, serial apply
    # =========================================================================

    async def _process_batch(
        self,
        engine: GameEngine,
        agents: dict[str, PlayerAgent],
        batch: list[str],
        phase: str,
        recorder: GameRecorder,
        max_concurrency: int,
    ) -> None:
        """Process a batch of players. Single player = serial, multiple = concurrent."""
        if len(batch) == 1:
            await self._process_serial(engine, agents, batch[0], phase, recorder)
            return

        # --- Concurrent mode ---
        logger.info("[%s] Concurrent batch: %d players, max_concurrency=%d",
                     phase, len(batch), max_concurrency)

        # 1. Snapshot context for all agents BEFORE any action (fairness)
        contexts: dict[str, dict] = {}
        for pid in batch:
            contexts[pid] = {
                "strategy": engine.get_agent_strategy(pid),
                "public_state": engine.get_public_state(),
                "private_info": engine.get_private_info(pid),
                "available_actions": engine.get_available_actions(pid),
                "rules_prompt": engine.get_game_rules_prompt(),
                "tools_schema": engine.get_tools_schema(),
            }

        # 2. Parallel think with semaphore
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
                    )
                    return (pid, response, None)
                except Exception as e:
                    logger.exception("Concurrent think failed for %s", pid)
                    return (pid, None, e)

        results = await asyncio.gather(*[think_with_limit(pid) for pid in batch])

        # 3. Serial apply + record + broadcast
        for pid, response, error in results:
            if error is not None or response is None:
                logger.warning("Using fallback response for %s", pid)
                response = agents[pid]._fallback_response(
                    contexts[pid]["available_actions"], 0,
                )

            try:
                engine.apply_action(pid, response.action)
            except Exception as e:
                logger.warning("apply_action failed for %s: %s, skipping", pid, e)
                continue

            log_msg = engine.format_action_log(pid, response.action)
            logger.info(log_msg)

            event = self._build_event(pid, response, agents[pid], phase)
            recorder.record_event(event)

            self._broadcast_action(engine, agents, pid, response.action)

            self.event_bus.emit("player_action", {
                "player_id": pid,
                "action": response.action.model_dump(),
            })

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

        engine.apply_action(player_id, response.action)

        log_msg = engine.format_action_log(player_id, response.action)
        logger.info(log_msg)

        event = self._build_event(player_id, response, agents[player_id], phase)
        recorder.record_event(event)

        self._broadcast_action(engine, agents, player_id, response.action)

        self.event_bus.emit("player_action", {
            "player_id": player_id,
            "action": response.action.model_dump(),
        })

    # =========================================================================
    # Agent interaction
    # =========================================================================

    async def _agent_think(
        self, engine: GameEngine, agent: PlayerAgent, player_id: str, strategy,
    ) -> AgentResponse:
        """Execute LLM thinking only — no engine state mutation."""
        public_state = engine.get_public_state()
        private_info = engine.get_private_info(player_id)
        available_actions = engine.get_available_actions(player_id)
        rules_prompt = engine.get_game_rules_prompt()
        tools_schema = engine.get_tools_schema()

        return await agent.think_and_act(
            game_rules_prompt=rules_prompt,
            public_state=public_state,
            private_info=private_info,
            available_actions=available_actions,
            tools_schema=tools_schema,
            strategy=strategy,
        )

    # =========================================================================
    # Helpers
    # =========================================================================

    def _broadcast_action(
        self, engine: GameEngine, agents: dict[str, PlayerAgent],
        player_id: str, action,
    ) -> None:
        """Broadcast action summary to appropriate players per engine rules."""
        targets = engine.get_broadcast_targets(player_id, action)
        if targets is None:
            target_ids = list(agents.keys())
        else:
            target_ids = targets

        if not target_ids:
            return

        summary = engine.format_public_summary(player_id, action)
        for pid in target_ids:
            if pid in agents:
                agents[pid].update_public_memory(summary)

    def _build_event(
        self, player_id: str, response: AgentResponse, agent: PlayerAgent, phase: str,
    ) -> GameEvent:
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
            # Build voice_config from player configs (only for players with explicit voice)
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
