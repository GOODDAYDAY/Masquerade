"""Thinker node — analyzes the game situation and generates strategy.

Uses game-specific prompt template from AgentStrategy (injected via state).
Payload construction is generic: uses tools_schema to determine field names.
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.nodes.base import build_node_messages
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.thinker")

# Heuristics for identifying player-target fields
_TARGET_NAME_HINTS = ("target", "player_id")
_TARGET_DESC_HINTS = ("玩家", "player", "ID")


async def thinker_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Analyze the situation and propose a strategy using game-specific prompt."""
    # Build thinker prompt with game-specific template
    # Note: thinker prompt template already includes {public_state} and {private_info}
    # placeholders, so we pass include_public_state=False to avoid duplication
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

    # Thinker's prompt template already embeds public_state and private_info,
    # so we only add memory + alive players via base builder
    messages = build_node_messages(
        state, user_prompt,
        include_memory=True,
        include_public_state=False,  # already in prompt template
        include_private_info=False,  # already in prompt template
    )

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

    # Log the thinking process
    analysis_str = json.dumps(analysis, ensure_ascii=False) if isinstance(analysis, dict) else str(analysis)
    strategy_str = json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy)
    logger.info("[%s] Thinker — situation_analysis: %s", player_id, analysis_str[:200])
    logger.info("[%s] Thinker — strategy: %s", player_id, strategy_str[:200])
    logger.info("[%s] Thinker → action=%s, content='%s'",
                player_id, action_type, str(action_content)[:100])

    tools_schema = state.get("tools_schema", [])
    alive_players = state.get("public_state", {}).get("alive_players", [])
    payload = _build_payload(action_type, action_content, tools_schema, alive_players)

    return {
        "situation_analysis": analysis,
        "strategy": strategy,
        "final_action_type": action_type,
        "final_action_payload": payload,
        "expression": expression,
    }


def _is_player_target(field_name: str, description: str) -> bool:
    """Heuristic: does this field represent a player target?"""
    if any(hint in field_name.lower() for hint in _TARGET_NAME_HINTS):
        return True
    if any(hint in description for hint in _TARGET_DESC_HINTS):
        return True
    return False


def _extract_player_name(text: str, alive_players: list[str]) -> str:
    """Extract a player name from potentially long text.

    If the text contains an alive player's name, return the first match.
    Otherwise return the text stripped and truncated.
    """
    text = str(text).strip()
    # Direct match
    if text in alive_players:
        return text
    # Search for any alive player name in the text
    for name in alive_players:
        if name in text:
            return name
    # Fallback: return first line, stripped
    first_line = text.split("\n")[0].strip()
    return first_line[:50] if first_line else text[:50]


def _build_payload(action_type: str, content: str, tools_schema: list[dict],
                   alive_players: list[str] | None = None) -> dict:
    """Build action payload using tools_schema to determine field names.

    Finds the matching tool definition, then fills the first required field
    with the LLM's action_content. For player-target fields, extracts just
    the player name from potentially long text.
    """
    # Find matching tool
    tool_def = None
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == action_type:
            tool_def = tool
            break

    if not tool_def:
        # Fallback: guess based on content
        return {"content": content}

    params = tool_def.get("function", {}).get("parameters", {})
    required = params.get("required", [])
    properties = params.get("properties", {})

    if not required:
        return {"content": content}

    # Build payload: put action_content into the first required field
    # For player-target fields, clean the content to extract just the name
    payload = {}
    content_placed = False
    for field_name in required:
        if not content_placed:
            prop = properties.get(field_name, {})
            desc = prop.get("description", "")
            if _is_player_target(field_name, desc) and alive_players:
                payload[field_name] = _extract_player_name(content, alive_players)
            else:
                payload[field_name] = content
            content_placed = True
        else:
            payload[field_name] = ""

    return payload
