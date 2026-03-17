"""Optimizer node — polishes the final output to sound natural and human-like.

Uses game-specific prompt from AgentStrategy (injected via state).
Uses tools_schema to generically determine which field to optimize
and whether to skip LLM call for target-only actions.
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.nodes.base import build_node_messages
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.optimizer")

# Positive-match hints: fields with these description keywords get LLM polishing.
_OPTIMIZE_DESC_HINTS = ("发言", "内容", "说", "看法", "推理", "遗言", "动作", "手势")


def _get_content_field(action_type: str, tools_schema: list[dict]) -> str | None:
    """Find the text content field that benefits from LLM polishing.

    Uses positive matching: only fields whose description contains speech/content
    keywords (发言, 内容, 说, etc.) are considered optimizable.
    Fields like 'gesture' (动作描述) are intentionally excluded.
    Returns None if no optimizable field found — optimizer will skip LLM call.
    """
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == action_type:
            params = tool.get("function", {}).get("parameters", {})
            required = params.get("required", [])
            properties = params.get("properties", {})
            for field_name in required:
                prop = properties.get(field_name, {})
                desc = prop.get("description", "")
                if any(hint in desc for hint in _OPTIMIZE_DESC_HINTS):
                    return field_name
            return None
    return None


async def optimizer_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Polish the action content using game-specific optimization prompt."""
    action_type = state.get("final_action_type", "")
    player_id = state.get("player_id", "?")
    tools_schema = state.get("tools_schema", [])

    # Determine if this action has text content to optimize
    content_field = _get_content_field(action_type, tools_schema)

    # Target-only actions (vote, protect, wolf_kill, etc.): skip LLM optimization
    if content_field is None:
        strategy_tip = _extract_short_tip(state.get("strategy", ""))
        logger.info("[%s] Optimizer: skipping LLM (target-only action: %s), tip='%s'",
                    player_id, action_type, strategy_tip[:40])
        return {
            "optimized_content": json.dumps(state.get("final_action_payload", {}), ensure_ascii=False),
            "strategy_tip": strategy_tip,
        }

    # Text-content actions (speak, wolf_discuss, last_words, etc.): optimize via LLM
    payload = state.get("final_action_payload", {})
    raw_content = payload.get(content_field, "")

    prompt_template = state.get("optimizer_prompt", "")
    prompt = prompt_template.format(
        persona=state.get("persona", "普通玩家"),
        situation_analysis=state.get("situation_analysis", ""),
        action_content=raw_content,
        action_type=action_type,
    )

    prompt += '\n\n**反幻觉规则（严格执行）：你只能引用游戏状态中实际存在的发言和事件。如果某人还没发言，不能编造他说过的话。如果是第一个发言者，不要引用任何人的"发言"。关键信息（查验结果、投票目标、玩家名字）必须与原始内容保持一致，不能更改。**'

    # Optimizer gets full context: game rules + memory + public_state + private_info
    messages = build_node_messages(
        state, prompt,
        include_memory=True,
        include_public_state=True,
        include_private_info=True,
    )

    response = await llm_client.chat(messages, temperature=0.7)

    optimized = raw_content
    expression = state.get("expression", "neutral")
    strategy_tip = ""

    try:
        json_str = response
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        parsed = json.loads(json_str.strip())
        optimized = parsed.get("optimized_content", raw_content)
        expression = parsed.get("expression", expression)
        strategy_tip = parsed.get("strategy_tip", "")
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse optimizer JSON, using original content")
        strategy_tip = _extract_short_tip(state.get("strategy", ""))

    # Update the content field in payload
    updated_payload = dict(state.get("final_action_payload", {}))
    updated_payload[content_field] = optimized

    logger.info("[%s] Optimizer → content='%s', expression=%s",
                 player_id, str(optimized)[:60], expression)
    logger.info("[%s] Optimizer → strategy_tip='%s'", player_id, strategy_tip[:40] if strategy_tip else "")

    return {
        "optimized_content": optimized,
        "expression": expression,
        "final_action_payload": updated_payload,
        "strategy_tip": strategy_tip,
    }


def _extract_short_tip(strategy_text: str) -> str:
    """Extract a short tip from the thinker's raw strategy text (fallback)."""
    if not strategy_text:
        return ""
    if isinstance(strategy_text, dict):
        strategy_text = str(strategy_text)
    # Take first sentence, max 50 chars
    text = strategy_text.strip()
    for sep in ("。", "，", "\n", ". ", ", "):
        if sep in text:
            text = text[:text.index(sep)]
            break
    return text[:50]
