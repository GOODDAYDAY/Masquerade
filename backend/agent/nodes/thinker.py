"""Thinker node — analyzes the game situation and generates strategy.

Uses game-specific prompt template from AgentStrategy (injected via state).
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.thinker")


async def thinker_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Analyze the situation and propose a strategy using game-specific prompt."""
    messages = list(state.get("memory_context", []))

    system_msg = state.get("game_rules_prompt", "") + "\n\n" + state.get("persona", "")
    messages.insert(0, {"role": "system", "content": system_msg})

    # Use the game-specific thinker prompt
    prompt_template = state.get("thinker_prompt", "")
    user_prompt = prompt_template.format(
        player_id=state.get("player_id", ""),
        private_info=json.dumps(state.get("private_info", {}), ensure_ascii=False),
        public_state=json.dumps(state.get("public_state", {}), ensure_ascii=False),
        available_actions=state.get("available_actions", []),
    )

    # Include evaluator feedback on retry
    feedback = state.get("evaluation_feedback", "")
    if feedback:
        user_prompt += "\n\n上次策略被评估为不够好，反馈如下：\n" + feedback
        user_prompt += "\n请重新分析并改进你的策略。"

    messages.append({"role": "user", "content": user_prompt})

    player_id = state.get("player_id", "?")
    retry_count = state.get("retry_count", 0)
    if retry_count > 0:
        logger.info("[%s] Thinker: retrying (attempt %d), feedback: %s",
                     player_id, retry_count + 1, feedback[:100] if feedback else "")
    else:
        logger.info("[%s] Thinker: analyzing situation...", player_id)

    response = await llm_client.chat(messages, temperature=0.8)

    # Parse JSON response
    analysis = ""
    strategy = ""
    action_type = ""
    action_content = ""
    expression = "neutral"

    try:
        json_str = response
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        parsed = json.loads(json_str.strip())
        analysis = parsed.get("situation_analysis", response)
        strategy = parsed.get("strategy", "")
        action_type = parsed.get("action_type", "")
        action_content = parsed.get("action_content", "")
        expression = parsed.get("expression", "neutral")
    except (json.JSONDecodeError, IndexError):
        logger.warning("[%s] Thinker: failed to parse JSON, using raw response", player_id)
        analysis = response
        available = state.get("available_actions", [])
        action_type = available[0] if available else "speak"

    # Log the full thinking process
    analysis_str = json.dumps(analysis, ensure_ascii=False) if isinstance(analysis, dict) else str(analysis)
    strategy_str = json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy)
    logger.info("[%s] Thinker — situation_analysis: %s", player_id, analysis_str[:200])
    logger.info("[%s] Thinker — strategy: %s", player_id, strategy_str[:200])
    if action_type == "speak":
        logger.info("[%s] Thinker → action=speak, content='%s'",
                     player_id, str(action_content)[:100])
    elif action_type == "vote":
        logger.info("[%s] Thinker → action=vote, target=%s", player_id, action_content)
    else:
        logger.info("[%s] Thinker → action=%s", player_id, action_type)

    return {
        "situation_analysis": analysis,
        "strategy": strategy,
        "final_action_type": action_type,
        "final_action_payload": _build_payload(action_type, action_content),
        "expression": expression,
    }


def _build_payload(action_type: str, content: str) -> dict:
    """Build action payload based on action type."""
    if action_type == "speak":
        return {"content": content}
    if action_type == "vote":
        return {"target_player_id": content}
    return {"content": content}
