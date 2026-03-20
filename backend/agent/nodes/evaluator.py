"""Evaluator node — assesses the proposed strategy and decides if retry is needed.

Two-layer evaluation:
  1. Programmatic validation — checks action legality using tools_schema from engine
  2. LLM scoring — uses game-specific prompt to evaluate strategy quality

Validation is fully generic: it reads the engine's tools_schema to determine
required fields and player-target fields. No game-specific knowledge needed.
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.nodes.base import (
    build_node_messages,
    find_tool,
    has_speech_field,
    is_player_field,
    parse_llm_json,
)
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.evaluator")

_DEFAULT_THRESHOLD = 6.0
_DEFAULT_MAX_RETRIES = 2


async def evaluator_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Evaluate the proposed strategy — first programmatically, then via LLM."""
    player_id = state.get("player_id", "?")
    retry_count = state.get("retry_count", 0)

    # 1. Programmatic validation — check action legality against tools_schema
    rejection = _run_programmatic_validation(state, player_id)
    if rejection:
        return _build_rejection(rejection, retry_count)

    # 2. Target-only actions (vote, protect): auto-pass, no LLM needed
    if not has_speech_field(state.get("final_action_type", ""), state.get("tools_schema", [])):
        return _auto_pass_target_only(state, player_id, retry_count)

    # 3. Speech actions: LLM scoring for quality assessment
    return await _run_llm_evaluation(state, llm_client, player_id, retry_count)


def should_retry(state: AgentState) -> str:
    """Conditional edge: decide whether to retry thinking or proceed."""
    score = state.get("evaluation_score", _DEFAULT_THRESHOLD)
    retry_count = state.get("retry_count", 0)
    threshold = state.get("evaluation_threshold", _DEFAULT_THRESHOLD)
    max_retries = state.get("max_retries_limit", _DEFAULT_MAX_RETRIES)
    player_id = state.get("player_id", "?")

    if score < threshold and retry_count <= max_retries:
        logger.info("[%s] Evaluator: score %.1f < %.1f, routing back to Thinker (retry %d/%d)",
                     player_id, score, threshold, retry_count, max_retries)
        return "retry"

    if retry_count > max_retries:
        logger.warning("[%s] Evaluator: max retries (%d) reached, force-fixing if needed",
                        player_id, max_retries)
        _force_fix_action(state)
    else:
        logger.info("[%s] Evaluator: PASSED → proceeding to Optimizer", player_id)

    return "proceed"


# ══════════════════════════════════════════════
#  Private step methods — evaluation paths
# ══════════════════════════════════════════════

def _run_programmatic_validation(state: AgentState, player_id: str) -> str | None:
    """Run programmatic validation and return error message or None."""
    error = _validate_action(state)
    if error:
        logger.warning("[%s] Evaluator: REJECTED — %s", player_id, error)
    return error


def _build_rejection(error: str, retry_count: int) -> dict:
    """Build rejection result for invalid actions."""
    return {
        "evaluation_score": 0.0,
        "evaluation_feedback": error,
        "retry_count": retry_count + 1,
    }


def _auto_pass_target_only(state: AgentState, player_id: str, retry_count: int) -> dict:
    """Auto-pass target-only actions that passed programmatic validation."""
    threshold = state.get("evaluation_threshold", _DEFAULT_THRESHOLD)
    logger.info("[%s] Evaluator: programmatic validation PASSED, skipping LLM (target-only action)", player_id)
    return {
        "evaluation_score": threshold,
        "evaluation_feedback": "",
        "retry_count": retry_count + 1,
    }


async def _run_llm_evaluation(
    state: AgentState, llm_client: LLMClient, player_id: str, retry_count: int,
) -> dict:
    """Run LLM scoring for speech/content actions."""
    # 1. Build evaluator prompt with GRG conflicts + focus reminder
    prompt = _build_evaluator_prompt(state)
    # 2. Wrap into LLM messages with memory + public state
    messages = _build_evaluator_messages(state, prompt)
    # 3. Call LLM for quality scoring
    response = await llm_client.chat(messages, temperature=0.3)
    # 4. Parse score and feedback from JSON response
    score, feedback = _parse_evaluator_response(response, state)
    _log_evaluation_result(player_id, score, feedback)

    return {
        "evaluation_score": score,
        "evaluation_feedback": feedback,
        "retry_count": retry_count + 1,
    }


# ══════════════════════════════════════════════
#  Private step methods — prompt building
# ══════════════════════════════════════════════

def _build_evaluator_prompt(state: AgentState) -> str:
    """Build the evaluator prompt from template and context."""
    prompt = _format_evaluator_template(state)
    prompt = _append_grg_evaluator_context(prompt, state)
    prompt = _append_evaluation_focus_reminder(prompt, state)
    return prompt


def _format_evaluator_template(state: AgentState) -> str:
    """Fill the game-specific evaluator prompt template."""
    template = state.get("evaluator_prompt", "")
    action_payload_str = json.dumps(state.get("final_action_payload", {}), ensure_ascii=False)
    situation_analysis = state.get("situation_analysis", "")
    strategy = state.get("strategy", "")
    return template.format(
        situation_analysis=json.dumps(situation_analysis, ensure_ascii=False) if isinstance(situation_analysis, dict) else str(situation_analysis),
        strategy=json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy),
        action_type=state.get("final_action_type", ""),
        action_payload=action_payload_str,
        private_info=json.dumps(state.get("private_info", {}), ensure_ascii=False),
    )


def _append_grg_evaluator_context(prompt: str, state: AgentState) -> str:
    """Append graph reasoning conflicts if available."""
    grg_evaluator = state.get("grg_evaluator_context", "")
    if grg_evaluator:
        prompt += "\n\n" + grg_evaluator
    return prompt


def _append_evaluation_focus_reminder(prompt: str, state: AgentState) -> str:
    """Append reminder to evaluate action_payload, not strategy text."""
    action_payload_str = json.dumps(state.get("final_action_payload", {}), ensure_ascii=False)
    prompt += (
        '\n\n**评估重点提醒：你评估的对象是上面的「操作内容」(action_payload)，即：%s。'
        '不要把「局势分析」或「策略」中的文字误认为是操作内容。'
        '如果操作内容是纯动作描述且不包含语言文字，就应该判定通过。**'
        % action_payload_str
    )
    return prompt


def _build_evaluator_messages(state: AgentState, prompt: str) -> list[dict]:
    """Build LLM messages with memory and public state context."""
    return build_node_messages(
        state, prompt,
        include_memory=True,
        include_public_state=True,
        include_private_info=False,
    )


# ══════════════════════════════════════════════
#  Private step methods — response parsing
# ══════════════════════════════════════════════

def _parse_evaluator_response(response: str, state: AgentState) -> tuple[float, str]:
    """Parse LLM JSON response into score and feedback."""
    threshold = state.get("evaluation_threshold", _DEFAULT_THRESHOLD)
    try:
        parsed = parse_llm_json(response)
        return float(parsed.get("score", threshold)), parsed.get("feedback", "")
    except (json.JSONDecodeError, IndexError, ValueError):
        logger.warning("Failed to parse evaluator JSON output, defaulting to pass")
        return threshold, ""


def _log_evaluation_result(player_id: str, score: float, feedback: str) -> None:
    """Log the evaluation score and feedback."""
    feedback_preview = feedback[:80] if feedback else ""
    logger.info("[%s] Evaluator → score=%.1f, feedback='%s'", player_id, score, feedback_preview)


# ══════════════════════════════════════════════
#  Programmatic validation — fully game-agnostic
# ══════════════════════════════════════════════

def _validate_action(state: AgentState) -> str | None:
    """Validate action using tools_schema. Returns None if valid, or error message."""
    action_type = state.get("final_action_type", "")
    available_actions = state.get("available_actions", [])

    error = _check_action_type(action_type, available_actions)
    if error:
        return error

    return _check_payload_fields(state)


def _check_action_type(action_type: str, available_actions: list[str]) -> str | None:
    """Check that action_type is in available actions."""
    if action_type not in available_actions:
        return "action_type '%s' is not available. Available actions: %s" % (action_type, available_actions)
    return None


def _check_payload_fields(state: AgentState) -> str | None:
    """Validate payload fields against tools_schema."""
    action_type = state.get("final_action_type", "")
    payload = state.get("final_action_payload", {})
    player_id = state.get("player_id", "")
    public_state = state.get("public_state", {})
    tools_schema = state.get("tools_schema", [])

    tool_def = find_tool(tools_schema, action_type)
    if not tool_def:
        return None

    params = tool_def.get("function", {}).get("parameters", {})
    required = params.get("required", [])
    properties = params.get("properties", {})
    alive = public_state.get("alive_players", [])

    for field_name in required:
        error = _validate_field(action_type, field_name, payload, properties, player_id, alive)
        if error:
            return error

    return None


def _validate_field(
    action_type: str, field_name: str, payload: dict,
    properties: dict, player_id: str, alive: list[str],
) -> str | None:
    """Validate a single required field."""
    value = payload.get(field_name, "")
    prop_def = properties.get(field_name, {})
    description = prop_def.get("description", "")

    if str(value).strip() == "skip":
        return None

    if not value or not str(value).strip():
        return "%s: required field '%s' is empty" % (action_type, field_name)

    if is_player_field(field_name, description):
        return _validate_player_target(action_type, field_name, value, player_id, alive)

    return None


def _validate_player_target(
    action_type: str, field_name: str, value: str, player_id: str, alive: list[str],
) -> str | None:
    """Validate a player-target field."""
    if value == player_id and action_type != "protect":
        valid_targets = [p for p in alive if p != player_id]
        return "%s: cannot target yourself ('%s'). Valid targets: %s" % (action_type, value, valid_targets)

    if alive and value not in alive:
        valid_targets = [p for p in alive if p != player_id]
        return "%s: target '%s' is not alive or does not exist. Valid targets: %s" % (action_type, value, valid_targets)

    return None


# ══════════════════════════════════════════════
#  Force-fix — last resort for invalid actions
# ══════════════════════════════════════════════

def _force_fix_action(state: AgentState) -> None:
    """Last-resort fix for invalid actions using tools_schema."""
    _fix_action_type(state)
    _fix_payload_fields(state)


def _fix_action_type(state: AgentState) -> None:
    """Fix action_type if not in available_actions."""
    action_type = state.get("final_action_type", "")
    available_actions = state.get("available_actions", [])
    player_id = state.get("player_id", "")
    tools_schema = state.get("tools_schema", [])

    if available_actions and action_type not in available_actions:
        old_type = action_type
        action_type = available_actions[0]
        state["final_action_type"] = action_type
        logger.warning("[%s] Force-fixed action_type: '%s' → '%s'", player_id, old_type, action_type)

        tool_def = find_tool(tools_schema, action_type)
        if tool_def:
            payload = state.get("final_action_payload", {})
            params = tool_def.get("function", {}).get("parameters", {})
            required = params.get("required", [])
            new_payload = {f: payload.get(f, "") for f in required}
            state["final_action_payload"] = new_payload


def _fix_payload_fields(state: AgentState) -> None:
    """Fix invalid payload fields (empty text, bad targets)."""
    action_type = state.get("final_action_type", "")
    payload = state.get("final_action_payload", {})
    player_id = state.get("player_id", "")
    public_state = state.get("public_state", {})
    tools_schema = state.get("tools_schema", [])

    alive = public_state.get("alive_players", [])
    valid_targets = [p for p in alive if p != player_id]

    tool_def = _find_tool(tools_schema, action_type)
    if not tool_def:
        return

    params = tool_def.get("function", {}).get("parameters", {})
    required = params.get("required", [])
    properties = params.get("properties", {})
    fixed = False

    for field_name in required:
        value = payload.get(field_name, "")
        prop_def = properties.get(field_name, {})
        description = prop_def.get("description", "")

        if is_player_field(field_name, description):
            if not value or value == player_id or (alive and value not in alive):
                if valid_targets:
                    old_value = value
                    payload[field_name] = valid_targets[0]
                    fixed = True
                    logger.warning("[%s] Force-fixed %s.%s: '%s' → '%s'",
                                   player_id, action_type, field_name, old_value, valid_targets[0])
        else:
            if not value or not str(value).strip():
                payload[field_name] = "..."
                fixed = True
                logger.warning("[%s] Force-fixed %s.%s: empty → '...'",
                               player_id, action_type, field_name)

    if fixed:
        state["final_action_payload"] = payload


