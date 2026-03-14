"""PlayerAgent — the public facade for a single AI player.

Externally, the agent exposes a simple think_and_act interface.
Internally, it orchestrates a LangGraph workflow with multiple decision nodes.
Game-specific strategy (prompt templates) is injected by the orchestrator.
"""

import time

from backend.agent.graph import build_player_graph
from backend.agent.llm_client import LLMClient
from backend.agent.memory import PlayerMemory
from backend.agent.models import AgentResponse
from backend.agent.state import AgentState
from backend.agent.strategy import AgentStrategy
from backend.core.config import PlayerConfig
from backend.core.logging import get_logger
from backend.engine.models import Action

logger = get_logger("agent.player")


class PlayerAgent:
    """AI player that uses a LangGraph multi-node workflow for decision-making."""

    def __init__(self, player_id: str, config: PlayerConfig) -> None:
        self.player_id = player_id
        self.config = config
        self.memory = PlayerMemory()

        self.llm_client = LLMClient(
            model=config.model,
            api_base=config.api_base,
            api_key=config.api_key,
        )
        self.graph = build_player_graph(self.llm_client)

        logger.info("PlayerAgent created: id=%s, model=%s", player_id, config.model)

    async def think_and_act(
        self,
        game_rules_prompt: str,
        public_state: dict,
        private_info: dict,
        available_actions: list[str],
        tools_schema: list[dict],
        strategy: AgentStrategy,
    ) -> AgentResponse:
        """Run the full decision pipeline and return a structured response.

        The strategy parameter carries game-specific prompt templates,
        injected by the orchestrator from the engine.
        """
        start_time = time.monotonic()

        # Build initial state for the LangGraph
        initial_state: AgentState = {
            "game_rules_prompt": game_rules_prompt,
            "public_state": public_state,
            "private_info": private_info,
            "available_actions": available_actions,
            "tools_schema": tools_schema,
            "persona": self.config.persona,
            "memory_context": self.memory.build_context_messages(),
            "retry_count": 0,
            "evaluation_feedback": "",
            # Strategy prompts from engine
            "thinker_prompt": strategy.thinker_prompt,
            "evaluator_prompt": strategy.evaluator_prompt,
            "optimizer_prompt": strategy.optimizer_prompt,
            "evaluation_threshold": strategy.evaluation_threshold,
            "max_retries_limit": strategy.max_retries,
        }

        # Invoke the LangGraph workflow
        try:
            result = await self.graph.ainvoke(initial_state)
        except Exception as e:
            logger.exception("Graph execution failed for player %s: %s", self.player_id, e)
            return self._fallback_response(available_actions, start_time)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Extract results from the final graph state
        action_type = result.get("final_action_type", available_actions[0] if available_actions else "speak")
        action_payload = result.get("final_action_payload", {})

        # Build thinking summary from all stages
        thinking_parts = []
        if result.get("situation_analysis"):
            thinking_parts.append("【局势分析】" + result["situation_analysis"])
        if result.get("strategy"):
            thinking_parts.append("【策略】" + result["strategy"])
        if result.get("evaluation_feedback"):
            thinking_parts.append("【评估反馈】" + result["evaluation_feedback"])
        full_thinking = "\n".join(thinking_parts) if thinking_parts else "No detailed thinking"

        # Store thinking in private memory
        self.memory.add_private(full_thinking)

        action = Action(
            type=action_type,
            player_id=self.player_id,
            payload=action_payload,
        )

        logger.info(
            "Player %s decided: action=%s, duration=%dms, eval_score=%.1f",
            self.player_id, action_type, elapsed_ms,
            result.get("evaluation_score", 0),
        )

        return AgentResponse(
            thinking=full_thinking,
            action=action,
            expression=result.get("expression", "neutral"),
            thinking_duration_ms=elapsed_ms,
        )

    def update_public_memory(self, event_summary: str) -> None:
        """Add a public event to this player's memory."""
        self.memory.add_public(event_summary)

    def _fallback_response(self, available_actions: list[str], start_time: float) -> AgentResponse:
        """Generate a minimal valid response when the graph fails."""
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        action_type = available_actions[0] if available_actions else "speak"

        if action_type == "speak":
            payload = {"content": "...让我想想。"}
        else:
            payload = {"target_player_id": ""}

        return AgentResponse(
            thinking="[Fallback] Graph execution failed, using default response",
            action=Action(type=action_type, player_id=self.player_id, payload=payload),
            expression="neutral",
            thinking_duration_ms=elapsed_ms,
        )
