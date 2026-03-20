"""Optimizer node — polishes the final output to sound natural and human-like.

Uses game-specific prompt from AgentStrategy (injected via state).
Uses tools_schema to generically determine which field to optimize
and whether to skip LLM call for target-only actions.
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.nodes.base import (
    build_node_messages,
    find_speech_field,
    parse_llm_json,
)
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.optimizer")


async def optimizer_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Polish the action content using game-specific optimization prompt."""
    player_id = state.get("player_id", "?")
    action_type = state.get("final_action_type", "")

    # 1. Check if this action has text content worth polishing
    content_field = find_speech_field(action_type, state.get("tools_schema", []))

    # 2a. Target-only actions (vote, protect): skip LLM, return as-is
    if content_field is None:
        return _skip_optimization(state, player_id, action_type)

    # 2b. Text-content actions (speak, last_words): run LLM optimization
    return await _run_optimization(state, llm_client, player_id, content_field)


# ══════════════════════════════════════════════
#  Private step methods — skip path
# ══════════════════════════════════════════════

def _skip_optimization(state: AgentState, player_id: str, action_type: str) -> dict:
    """Return unchanged payload for target-only actions (vote, protect, etc.)."""
    strategy_tip = _extract_short_tip(state.get("strategy", ""))
    logger.info("[%s] Optimizer: skipping LLM (target-only action: %s), tip='%s'",
                player_id, action_type, strategy_tip[:40])
    return {
        "optimized_content": json.dumps(state.get("final_action_payload", {}), ensure_ascii=False),
        "strategy_tip": strategy_tip,
    }


# ══════════════════════════════════════════════
#  Private step methods — optimization path
# ══════════════════════════════════════════════

async def _run_optimization(
    state: AgentState, llm_client: LLMClient, player_id: str, content_field: str,
) -> dict:
    """Run full LLM optimization for text-content actions."""
    raw_content = state.get("final_action_payload", {}).get(content_field, "")
    # 1. Build prompt with strategy constraint + anti-hallucination rules
    prompt = _build_prompt(state, raw_content)
    # 2. Wrap into LLM messages with full game context
    messages = _build_messages(state, prompt)
    # 3. Call LLM for polished output
    response = await llm_client.chat(messages, temperature=0.7)
    # 4. Parse response and update payload with optimized content
    optimized, expression, strategy_tip = _parse_response(response, raw_content, state)
    updated_payload = _update_payload(state, content_field, optimized)
    _log_result(player_id, optimized, expression, strategy_tip)

    return {
        "optimized_content": optimized,
        "expression": expression,
        "final_action_payload": updated_payload,
        "strategy_tip": strategy_tip,
    }


def _build_prompt(state: AgentState, raw_content: str) -> str:
    """Build the optimizer prompt from template, strategy constraint, and anti-hallucination rules."""
    prompt = _format_prompt_template(state, raw_content)
    prompt = _append_strategy_constraint(prompt, state)
    prompt = _append_anti_hallucination_rules(prompt)
    return prompt


def _format_prompt_template(state: AgentState, raw_content: str) -> str:
    """Fill the game-specific optimizer prompt template."""
    template = state.get("optimizer_prompt", "")
    return template.format(
        persona=state.get("persona", "普通玩家"),
        situation_analysis=state.get("situation_analysis", ""),
        action_content=raw_content,
        action_type=state.get("final_action_type", ""),
    )


def _append_strategy_constraint(prompt: str, state: AgentState) -> str:
    """Append strategy direction constraint to prevent optimizer from changing strategy."""
    thinker_strategy = state.get("strategy", "")
    strategy_str = json.dumps(thinker_strategy, ensure_ascii=False) if isinstance(thinker_strategy, dict) else str(thinker_strategy)
    prompt += (
        '\n\n**策略遵循规则（最高优先级）：你的任务是润色，不是改变策略。'
        'Thinker 的策略方向是：「' + strategy_str[:200] + '」。'
        '你必须严格遵循这个策略方向进行润色。'
        '如果策略说"伪装成好人"，你就必须输出好人视角的发言，绝对不能暴露真实身份。'
        '如果策略说"质疑某人"，你就质疑那个人，不能改成支持。**'
    )
    return prompt


def _append_anti_hallucination_rules(prompt: str) -> str:
    """Append rules to prevent fabricating game events."""
    prompt += (
        '\n\n**反幻觉规则（严格执行）：你只能引用游戏状态中实际存在的发言和事件。'
        '如果某人还没发言，不能编造他说过的话。'
        '如果是第一个发言者，不要引用任何人的"发言"。'
        '关键信息（查验结果、投票目标、玩家名字）必须与原始内容保持一致，不能更改。**'
    )
    return prompt


def _build_messages(state: AgentState, prompt: str) -> list[dict]:
    """Build LLM messages with full context."""
    return build_node_messages(
        state, prompt,
        include_memory=True,
        include_public_state=True,
        include_private_info=True,
    )


def _parse_response(
    response: str, raw_content: str, state: AgentState,
) -> tuple[str, str, str]:
    """Parse LLM JSON response into optimized content, expression, and tip."""
    try:
        parsed = parse_llm_json(response)
        return (
            parsed.get("optimized_content", raw_content),
            parsed.get("expression", state.get("expression", "neutral")),
            parsed.get("strategy_tip", ""),
        )
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse optimizer JSON, using original content")
        return raw_content, state.get("expression", "neutral"), _extract_short_tip(state.get("strategy", ""))


def _update_payload(state: AgentState, content_field: str, optimized: str) -> dict:
    """Create updated payload with optimized content."""
    updated = dict(state.get("final_action_payload", {}))
    updated[content_field] = optimized
    return updated


def _log_result(player_id: str, optimized: str, expression: str, strategy_tip: str) -> None:
    """Log the optimization result."""
    logger.info("[%s] Optimizer → content='%s', expression=%s",
                 player_id, str(optimized)[:60], expression)
    logger.info("[%s] Optimizer → strategy_tip='%s'", player_id, strategy_tip[:40] if strategy_tip else "")


# ══════════════════════════════════════════════
#  Utility helpers
# ══════════════════════════════════════════════

def _extract_short_tip(strategy_text: str) -> str:
    """Extract a short tip from the thinker's raw strategy text (fallback)."""
    if not strategy_text:
        return ""
    if isinstance(strategy_text, dict):
        strategy_text = str(strategy_text)
    text = strategy_text.strip()
    for sep in ("。", "，", "\n", ". ", ", "):
        if sep in text:
            text = text[:text.index(sep)]
            break
    return text[:50]
