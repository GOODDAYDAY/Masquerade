"""Thinker node — analyzes the game situation and generates strategy.

Uses game-specific prompt template from AgentStrategy (injected via state).
Payload construction is generic: uses tools_schema to determine field names.
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.nodes.base import (
    build_node_messages,
    find_tool,
    is_player_field,
    parse_llm_json,
)
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.thinker")


async def thinker_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Analyze the situation and propose a strategy using game-specific prompt."""
    player_id = state.get("player_id", "?")

    # 1. Build prompt from template + GRG context + retry feedback
    user_prompt = _build_prompt(state)
    # 2. Wrap prompt into LLM message list with memory context
    messages = _build_messages(state, user_prompt)
    _log_start(player_id, state)
    # 3. Call LLM for situation analysis and strategy
    response = await llm_client.chat(messages, temperature=0.8)
    # 4. Parse JSON response into structured fields
    analysis, strategy, action_type, action_content, expression = _parse_response(response, state)
    _log_result(player_id, analysis, strategy, action_type, action_content)
    # 5. Convert action_content into engine-compatible payload via tools_schema
    payload = _build_payload(action_type, action_content, state)

    return {
        "situation_analysis": analysis,
        "strategy": strategy,
        "final_action_type": action_type,
        "final_action_payload": payload,
        "expression": expression,
    }


# ══════════════════════════════════════════════
#  Private step methods — prompt building
# ══════════════════════════════════════════════

def _build_prompt(state: AgentState) -> str:
    """Build the thinker prompt from template, GRG context, and retry feedback."""
    prompt = _format_prompt_template(state)
    prompt = _append_grg_context(prompt, state)
    prompt = _append_retry_feedback(prompt, state)
    return prompt


def _format_prompt_template(state: AgentState) -> str:
    """Fill the game-specific prompt template with state values."""
    template = state.get("thinker_prompt", "")
    return template.format(
        player_id=state.get("player_id", ""),
        private_info=json.dumps(state.get("private_info", {}), ensure_ascii=False),
        public_state=json.dumps(state.get("public_state", {}), ensure_ascii=False),
        available_actions=state.get("available_actions", []),
    )


def _append_grg_context(prompt: str, state: AgentState) -> str:
    """Append graph reasoning analysis if available."""
    grg_context = state.get("grg_thinker_context", "")
    if grg_context:
        prompt += "\n\n【图谱推理分析】\n" + grg_context
    return prompt


def _append_retry_feedback(prompt: str, state: AgentState) -> str:
    """Append evaluator feedback on retry."""
    feedback = state.get("evaluation_feedback", "")
    if feedback:
        prompt += "\n\n上次策略被评估为不够好，反馈如下：\n" + feedback
        prompt += "\n请重新分析并改进你的策略。"
    return prompt


def _build_messages(state: AgentState, user_prompt: str) -> list[dict]:
    """Build LLM messages via base builder (memory only, state already in template)."""
    return build_node_messages(
        state, user_prompt,
        include_memory=True,
        include_public_state=False,
        include_private_info=False,
    )


# ══════════════════════════════════════════════
#  Private step methods — response parsing
# ══════════════════════════════════════════════

def _parse_response(
    response: str, state: AgentState,
) -> tuple[str, str, str, str, str]:
    """Parse LLM JSON response into structured fields."""
    try:
        parsed = parse_llm_json(response)
        return (
            parsed.get("situation_analysis", response),
            parsed.get("strategy", ""),
            parsed.get("action_type", ""),
            parsed.get("action_content", ""),
            parsed.get("expression", "neutral"),
        )
    except (json.JSONDecodeError, IndexError):
        player_id = state.get("player_id", "?")
        logger.warning("[%s] Thinker: failed to parse JSON, using raw response", player_id)
        available = state.get("available_actions", [])
        action_type = available[0] if available else "speak"
        return response, "", action_type, "", "neutral"


# ══════════════════════════════════════════════
#  Private step methods — logging
# ══════════════════════════════════════════════

def _log_start(player_id: str, state: AgentState) -> None:
    """Log thinker start or retry."""
    retry_count = state.get("retry_count", 0)
    if retry_count > 0:
        feedback = state.get("evaluation_feedback", "")
        logger.info("[%s] Thinker: retrying (attempt %d), feedback: %s",
                     player_id, retry_count + 1, feedback[:100] if feedback else "")
    else:
        logger.info("[%s] Thinker: analyzing situation...", player_id)


def _log_result(
    player_id: str, analysis: str, strategy: str, action_type: str, action_content: str,
) -> None:
    """Log the thinking result summary."""
    analysis_str = json.dumps(analysis, ensure_ascii=False) if isinstance(analysis, dict) else str(analysis)
    strategy_str = json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy)
    logger.info("[%s] Thinker — situation_analysis: %s", player_id, analysis_str[:200])
    logger.info("[%s] Thinker — strategy: %s", player_id, strategy_str[:200])
    logger.info("[%s] Thinker → action=%s, content='%s'",
                player_id, action_type, str(action_content)[:100])


# ══════════════════════════════════════════════
#  Private step methods — payload building
# ══════════════════════════════════════════════

def _build_payload(action_type: str, content: str, state: AgentState) -> dict:
    """Build action payload using tools_schema to determine field names."""
    tools_schema = state.get("tools_schema", [])
    alive_players = state.get("public_state", {}).get("alive_players", [])
    tool_def = find_tool(tools_schema, action_type)

    if not tool_def:
        return {"content": content}

    params = tool_def.get("function", {}).get("parameters", {})
    required = params.get("required", [])
    properties = params.get("properties", {})

    if not required:
        return {"content": content}

    return _fill_required_fields(content, required, properties, alive_players)


def _fill_required_fields(
    content: str,
    required: list[str],
    properties: dict,
    alive_players: list[str],
) -> dict:
    """Fill required fields, placing content in the first field."""
    payload = {}
    content_placed = False
    for field_name in required:
        if not content_placed:
            prop = properties.get(field_name, {})
            desc = prop.get("description", "")
            if is_player_field(field_name, desc) and alive_players:
                payload[field_name] = _extract_player_name(content, alive_players)
            else:
                payload[field_name] = content
            content_placed = True
        else:
            payload[field_name] = ""
    return payload


def _extract_player_name(text: str, alive_players: list[str]) -> str:
    """Extract a player name from potentially long text."""
    text = str(text).strip()
    if text in alive_players:
        return text
    for name in alive_players:
        if name in text:
            return name
    first_line = text.split("\n")[0].strip()
    return first_line[:50] if first_line else text[:50]
