"""PlayerAgent — the public facade for a single AI player.

Externally, the agent exposes a simple think_and_act interface.
Internally, it orchestrates a LangGraph workflow with multiple decision nodes.
Game-specific strategy (prompt templates) is injected by the orchestrator.
"""

import json
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
        grg_thinker_context: str = "",
        grg_evaluator_context: str = "",
    ) -> AgentResponse:
        """Run the full decision pipeline and return a structured response."""
        start_time = time.monotonic()
        # 1. Assemble all inputs into LangGraph initial state
        initial_state = self._build_initial_state(
            game_rules_prompt, public_state, private_info,
            available_actions, tools_schema, strategy,
            grg_thinker_context, grg_evaluator_context,
        )
        # 2. Run LangGraph workflow (Thinker → Evaluator → Optimizer)
        result = await self._invoke_graph(initial_state, available_actions, start_time)
        # 3. Extract and assemble final response from graph output
        response = self._build_response(result, available_actions, start_time)
        # 4. Store thinking in private memory for next-round context
        self.memory.add_private(response.thinking)

        return response

    def update_public_memory(self, event_summary: str) -> None:
        """Add a public event to this player's memory."""
        self.memory.add_public(event_summary)

    # ══════════════════════════════════════════════
    #  Private step methods
    # ══════════════════════════════════════════════

    def _build_initial_state(
        self,
        game_rules_prompt: str,
        public_state: dict,
        private_info: dict,
        available_actions: list[str],
        tools_schema: list[dict],
        strategy: AgentStrategy,
        grg_thinker_context: str,
        grg_evaluator_context: str,
    ) -> AgentState:
        """Assemble the initial LangGraph state from all inputs."""
        return {
            "player_id": self.player_id,
            "game_rules_prompt": game_rules_prompt,
            "public_state": public_state,
            "private_info": private_info,
            "available_actions": available_actions,
            "tools_schema": tools_schema,
            "persona": self.config.persona,
            "memory_context": self.memory.build_context_messages(),
            "retry_count": 0,
            "evaluation_feedback": "",
            "grg_thinker_context": grg_thinker_context,
            "grg_evaluator_context": grg_evaluator_context,
            "thinker_prompt": strategy.thinker_prompt,
            "evaluator_prompt": strategy.evaluator_prompt,
            "optimizer_prompt": strategy.optimizer_prompt,
            "evaluation_threshold": strategy.evaluation_threshold,
            "max_retries_limit": strategy.max_retries,
        }

    async def _invoke_graph(
        self, initial_state: AgentState, available_actions: list[str], start_time: float,
    ) -> dict:
        """Invoke the LangGraph workflow, falling back on failure."""
        try:
            return await self.graph.ainvoke(initial_state)
        except Exception as e:
            logger.exception("Graph execution failed for player %s: %s", self.player_id, e)
            return self._build_fallback_result(available_actions)

    def _build_fallback_result(self, available_actions: list[str]) -> dict:
        """Build a minimal result dict when graph execution fails."""
        action_type = available_actions[0] if available_actions else "speak"
        return {
            "final_action_type": action_type,
            "final_action_payload": {"content": "..."},
            "situation_analysis": "[Fallback] Graph execution failed",
            "strategy": "",
            "evaluation_feedback": "",
            "expression": "neutral",
            "evaluation_score": 0,
            "strategy_tip": "",
        }

    def _build_response(
        self, result: dict, available_actions: list[str], start_time: float,
    ) -> AgentResponse:
        """Extract and assemble the final response from graph result."""
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        action_type = result.get("final_action_type", available_actions[0] if available_actions else "speak")
        action_payload = result.get("final_action_payload", {})
        full_thinking = self._assemble_thinking(result)

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
            strategy_tip=result.get("strategy_tip", ""),
        )

    def _assemble_thinking(self, result: dict) -> str:
        """Assemble the thinking summary from all stage outputs."""
        parts = []
        for label, key in [
            ("【局势分析】", "situation_analysis"),
            ("【策略】", "strategy"),
            ("【评估反馈】", "evaluation_feedback"),
        ]:
            val = result.get(key)
            if val:
                text = json.dumps(val, ensure_ascii=False) if isinstance(val, dict) else str(val)
                parts.append(label + text)
        return "\n".join(parts) if parts else "No detailed thinking"

    def _fallback_response(
        self, available_actions: list[str], start_time: float,
        tools_schema: list[dict] | None = None,
    ) -> AgentResponse:
        """Generate a minimal valid response when the graph fails."""
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        action_type = available_actions[0] if available_actions else "speak"
        payload = _build_fallback_payload(action_type, tools_schema or [])

        return AgentResponse(
            thinking="[Fallback] Graph execution failed, using default response",
            action=Action(type=action_type, player_id=self.player_id, payload=payload),
            expression="neutral",
            thinking_duration_ms=elapsed_ms,
        )


def _build_fallback_payload(action_type: str, tools_schema: list[dict]) -> dict:
    """Build a minimal valid payload from tools_schema for fallback responses."""
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == action_type:
            params = tool.get("function", {}).get("parameters", {})
            required = params.get("required", [])
            payload = {}
            for field_name in required:
                payload[field_name] = "..."
            return payload if payload else {"content": "..."}
    return {"content": "..."}
