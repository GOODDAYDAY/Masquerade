"""Game runner — orchestrates Engine + Agent + Recorder to drive a full game.

The runner is game-agnostic. It receives a game type name and a raw config dict.
The engine parses its own config. The runner only needs player IDs to create agents.
"""

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
from backend.engine.models import Action
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
        self.event_bus = EventBus()

    async def run(self) -> GameScript:
        """Execute a full game and return the recorded script."""
        logger.info("Starting game: type=%s", self.game_type)

        # 1. Create and setup engine — engine parses its own config
        engine_cls = get_game_engine(self.game_type)
        engine = engine_cls()

        # Extract player configs for agent creation, pass remaining config to engine
        player_configs = self._build_player_configs()
        player_ids = [pc.name for pc in player_configs]
        engine.setup(player_ids, self.game_config)

        # 2. Get game-specific agent strategy
        strategy = engine.get_agent_strategy()

        # 3. Create agents
        agents: dict[str, PlayerAgent] = {}
        for pc in player_configs:
            agents[pc.name] = PlayerAgent(player_id=pc.name, config=pc)

        # 4. Create recorder
        game_info = GameInfo(
            type=self.game_type,
            config=self.game_config,
            created_at=datetime.now(),
        )
        player_infos = []
        for pc in player_configs:
            role_info = engine.get_role_info(pc.name)
            player_infos.append(PlayerInfo(
                id=pc.name,
                name=pc.name,
                model=pc.model,
                persona=pc.persona,
                appearance=pc.appearance,
                role=role_info.get("role", ""),
                word=role_info.get("word", ""),
            ))
        recorder = GameRecorder(game_info, player_infos)

        # 5. Game loop
        self.event_bus.emit("game_start")
        round_count = 0

        while not engine.is_ended():
            public_state = engine.get_public_state()
            current_round = public_state.get("round_number", round_count + 1)
            recorder.start_round(current_round)
            self.event_bus.emit("round_start", {"round": current_round})
            round_count += 1
            logger.info("========== Round %d ==========", current_round)

            while engine.get_current_player() is not None and not engine.is_ended():
                current_player = engine.get_current_player()
                if not current_player:
                    break

                available = engine.get_available_actions(current_player)
                if not available:
                    break

                phase = engine.get_public_state().get("phase", "")
                logger.info("[%s] %s's turn (available: %s)", phase, current_player, available)

                agent_response = await self._agent_turn(
                    engine, agents[current_player], current_player, strategy
                )

                # Log the action content for visibility
                action = agent_response.action
                if action.type == "speak":
                    logger.info("[%s] %s says: %s", phase, current_player, action.payload.get("content", ""))
                elif action.type == "vote":
                    logger.info("[%s] %s votes for: %s", phase, current_player, action.payload.get("target_player_id", ""))

                event = self._build_event(
                    current_player, agent_response, agents[current_player], engine
                )
                recorder.record_event(event)

                # Broadcast public info — but NOT individual votes (secret ballot)
                if action.type != "vote":
                    summary = self._format_public_summary(current_player, agent_response.action)
                    for agent in agents.values():
                        agent.update_public_memory(summary)

                self.event_bus.emit("player_action", {
                    "player_id": current_player,
                    "action": agent_response.action.model_dump(),
                })

            # Record vote result and broadcast to all agents (public info)
            public_state = engine.get_public_state()
            vote_result = self._extract_vote_result(public_state)
            if vote_result:
                recorder.record_vote_result(vote_result)

                # Build detailed vote summary (who voted for whom is public)
                vote_history = public_state.get("vote_history", {})
                current_round_votes = vote_history.get(
                    max(vote_history.keys()), {}
                ) if vote_history else {}

                vote_lines = []
                for voter, target in current_round_votes.items():
                    vote_lines.append("%s → %s" % (voter, target))

                if vote_result.eliminated:
                    vote_summary = "投票详情: %s\n结果: %s 被淘汰" % (
                        ", ".join(vote_lines), vote_result.eliminated)
                    logger.info(">>> Votes: %s => %s eliminated!",
                                ", ".join(vote_lines), vote_result.eliminated)
                else:
                    vote_summary = "投票详情: %s\n结果: 平票，无人淘汰" % ", ".join(vote_lines)
                    logger.info(">>> Votes: %s => Tie, no elimination",
                                ", ".join(vote_lines))

                for agent in agents.values():
                    agent.update_public_memory(vote_summary)

        # 6. Game end
        result = engine.get_result()
        if result:
            recorder.set_result(GameResult(
                winner=result.winner,
                eliminated_order=result.eliminated_order,
                total_rounds=result.total_rounds,
            ))

        self.event_bus.emit("game_end", {"result": result})

        # 7. Save and return
        script = recorder.export()
        script_path = recorder.save(self.app_settings.scripts_dir)
        logger.info("========== Game Over ==========")
        if result:
            logger.info("Winner: %s | Rounds: %d | Eliminated: %s",
                        result.winner, result.total_rounds, ", ".join(result.eliminated_order))
        logger.info("Script saved: %s", script_path)

        # 8. Generate TTS audio
        await self._generate_tts(script_path)

        return script

    async def _agent_turn(self, engine, agent: PlayerAgent, player_id: str, strategy) -> AgentResponse:
        """Execute a single agent turn.

        The agent's internal LangGraph handles validation and retries.
        Runner simply passes context in and applies the result.
        """
        public_state = engine.get_public_state()
        private_info = engine.get_private_info(player_id)
        available_actions = engine.get_available_actions(player_id)
        rules_prompt = engine.get_game_rules_prompt()
        tools_schema = engine.get_tools_schema()

        response = await agent.think_and_act(
            game_rules_prompt=rules_prompt,
            public_state=public_state,
            private_info=private_info,
            available_actions=available_actions,
            tools_schema=tools_schema,
            strategy=strategy,
        )

        engine.apply_action(player_id, response.action)
        return response

    def _build_event(
        self, player_id: str, response: AgentResponse, agent: PlayerAgent, engine: GameEngine,
    ) -> GameEvent:
        public_state = engine.get_public_state()
        return GameEvent(
            player_id=player_id,
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

    def _format_public_summary(self, player_id: str, action: Action) -> str:
        if action.type == "speak":
            return "%s 说: %s" % (player_id, action.payload.get("content", ""))
        if action.type == "vote":
            return "%s 投票给了 %s" % (player_id, action.payload.get("target_player_id", ""))
        return "%s 执行了 %s" % (player_id, action.type)

    def _extract_vote_result(self, public_state: dict) -> VoteResult | None:
        eliminated = public_state.get("eliminated_players", [])
        last_eliminated = eliminated[-1] if eliminated else None
        return VoteResult(eliminated=last_eliminated)

    async def _generate_tts(self, script_path: str) -> None:
        """Generate TTS audio for the game script. Skips if edge-tts not installed."""
        try:
            from backend.tts.generate import generate_audio
            logger.info("Generating TTS audio...")
            manifest = await generate_audio(script_path)
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
