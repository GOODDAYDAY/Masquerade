"""Optimizer node — polishes the final output to sound natural and human-like.

Uses game-specific prompt from AgentStrategy (injected via state).
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.optimizer")


async def optimizer_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Polish the action content using game-specific optimization prompt."""
    action_type = state.get("final_action_type", "")

    player_id = state.get("player_id", "?")

    # Skip optimization for vote actions
    if action_type == "vote":
        logger.info("[%s] Optimizer: skipping (vote action)", player_id)
        return {
            "optimized_content": json.dumps(state.get("final_action_payload", {}), ensure_ascii=False),
        }

    payload = state.get("final_action_payload", {})
    raw_content = payload.get("content", "") or payload.get("target_player_id", "")

    prompt_template = state.get("optimizer_prompt", "")
    prompt = prompt_template.format(
        persona=state.get("persona", "普通玩家"),
        situation_analysis=state.get("situation_analysis", ""),
        action_content=raw_content,
        action_type=action_type,
    )

    messages = [{"role": "user", "content": prompt}]
    response = await llm_client.chat(messages, temperature=0.9)

    optimized = raw_content
    expression = state.get("expression", "neutral")

    try:
        json_str = response
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        parsed = json.loads(json_str.strip())
        optimized = parsed.get("optimized_content", raw_content)
        expression = parsed.get("expression", expression)
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse optimizer JSON, using original content")

    # Update the action payload with optimized content
    updated_payload = dict(state.get("final_action_payload", {}))
    if action_type == "speak":
        updated_payload["content"] = optimized

    logger.info("[%s] Optimizer → content='%s', expression=%s",
                 player_id, str(optimized)[:60], expression)

    return {
        "optimized_content": optimized,
        "expression": expression,
        "final_action_payload": updated_payload,
    }
