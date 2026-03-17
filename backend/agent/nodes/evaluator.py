"""Evaluator node — assesses the proposed strategy and decides if retry is needed.

Two-layer evaluation:
  1. Programmatic validation — checks action legality using tools_schema from engine
  2. LLM scoring — uses game-specific prompt to evaluate strategy quality

Validation is fully generic: it reads the engine's tools_schema to determine
required fields and player-target fields. No game-specific knowledge needed.
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.evaluator")

_DEFAULT_THRESHOLD = 6.0
_DEFAULT_MAX_RETRIES = 2

# Heuristics for identifying speech content fields (same as optimizer)
_SPEECH_DESC_HINTS = ("发言", "内容", "说", "看法", "推理", "遗言", "动作", "手势")

# Heuristics for identifying player-target fields
_TARGET_NAME_HINTS = ("target", "player_id")
_TARGET_DESC_HINTS = ("玩家", "player", "ID")


def _find_tool(tools_schema: list[dict], action_type: str) -> dict | None:
    """Find the tool definition matching the action type."""
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == action_type:
            return tool
    return None


def _is_player_field(field_name: str, description: str) -> bool:
    """Heuristic: does this field represent a player target?"""
    if any(hint in field_name.lower() for hint in _TARGET_NAME_HINTS):
        return True
    if any(hint in description for hint in _TARGET_DESC_HINTS):
        return True
    return False


def _validate_action(state: AgentState) -> str | None:
    """Programmatic validation using tools_schema — fully game-agnostic.

    Returns None if valid, or an error message string if invalid.
    """
    action_type = state.get("final_action_type", "")
    payload = state.get("final_action_payload", {})
    player_id = state.get("player_id", "")
    public_state = state.get("public_state", {})
    available_actions = state.get("available_actions", [])
    tools_schema = state.get("tools_schema", [])

    # Check action type is available
    if action_type not in available_actions:
        return "action_type '%s' is not available. Available actions: %s" % (action_type, available_actions)

    # Find matching tool definition from engine's tools_schema
    tool_def = _find_tool(tools_schema, action_type)
    if not tool_def:
        return None  # No schema to validate against — pass through

    params = tool_def.get("function", {}).get("parameters", {})
    required = params.get("required", [])
    properties = params.get("properties", {})
    alive = public_state.get("alive_players", [])

    for field_name in required:
        value = payload.get(field_name, "")
        prop_def = properties.get(field_name, {})
        description = prop_def.get("description", "")

        # "skip" is a valid sentinel for optional actions (e.g. hunter_shoot)
        if str(value).strip() == "skip":
            continue

        # Required field must not be empty
        if not value or not str(value).strip():
            return "%s: required field '%s' is empty" % (action_type, field_name)

        # Player-target field: validate against alive players
        if _is_player_field(field_name, description):
            # Guard (protect) is allowed to target self; all other actions cannot
            if value == player_id and action_type != "protect":
                valid_targets = [p for p in alive if p != player_id]
                return (
                    "%s: cannot target yourself ('%s'). Valid targets: %s"
                    % (action_type, value, valid_targets)
                )
            if alive and value not in alive:
                valid_targets = [p for p in alive if p != player_id]
                return (
                    "%s: target '%s' is not alive or does not exist. Valid targets: %s"
                    % (action_type, value, valid_targets)
                )

    return None


def _has_speech_content(state: AgentState) -> bool:
    """Check if the current action has a speech/content field worth LLM scoring."""
    action_type = state.get("final_action_type", "")
    tools_schema = state.get("tools_schema", [])
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == action_type:
            params = tool.get("function", {}).get("parameters", {})
            for field_name in params.get("required", []):
                prop = params.get("properties", {}).get(field_name, {})
                desc = prop.get("description", "")
                if any(hint in desc for hint in _SPEECH_DESC_HINTS):
                    return True
            return False
    return False


async def evaluator_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Evaluate the proposed strategy — first programmatically, then via LLM."""
    retry_count = state.get("retry_count", 0)

    player_id = state.get("player_id", "?")

    # Layer 1: Programmatic validation
    validation_error = _validate_action(state)
    if validation_error:
        logger.warning("[%s] Evaluator: REJECTED — %s", player_id, validation_error)
        return {
            "evaluation_score": 0.0,
            "evaluation_feedback": validation_error,
            "retry_count": retry_count + 1,
        }

    # Skip LLM scoring for target-only actions (protect, vote, wolf_kill, etc.)
    # Programmatic validation is sufficient for these — LLM scoring often hallucinates
    # rule violations (e.g. "consecutive guard" on first night). Only score speech-like actions.
    if not _has_speech_content(state):
        logger.info("[%s] Evaluator: programmatic validation PASSED, skipping LLM (target-only action)", player_id)
        threshold = state.get("evaluation_threshold", _DEFAULT_THRESHOLD)
        return {
            "evaluation_score": threshold,  # Auto-pass
            "evaluation_feedback": "",
            "retry_count": retry_count + 1,
        }

    # Layer 2: LLM scoring (only for speech/content actions)
    prompt_template = state.get("evaluator_prompt", "")
    situation_analysis = state.get("situation_analysis", "")
    strategy = state.get("strategy", "")

    action_payload_str = json.dumps(state.get("final_action_payload", {}), ensure_ascii=False)

    prompt = prompt_template.format(
        situation_analysis=json.dumps(situation_analysis, ensure_ascii=False) if isinstance(situation_analysis, dict) else str(situation_analysis),
        strategy=json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy),
        action_type=state.get("final_action_type", ""),
        action_payload=action_payload_str,
        private_info=json.dumps(state.get("private_info", {}), ensure_ascii=False),
    )

    # Prevent evaluator from confusing strategy analysis with actual payload
    prompt += (
        '\n\n**评估重点提醒：你评估的对象是上面的「操作内容」(action_payload)，即：%s。'
        '不要把「局势分析」或「策略」中的文字误认为是操作内容。'
        '如果操作内容是纯动作描述且不包含语言文字，就应该判定通过。**'
        % action_payload_str
    )

    # Evaluator gets full context — needs memory to verify factual claims,
    # needs public_state to cross-check references, needs private_info to catch
    # inconsistencies (e.g. seer reporting wrong check result)
    from backend.agent.nodes.base import build_node_messages
    messages = build_node_messages(
        state, prompt,
        include_memory=True,
        include_public_state=True,
        include_private_info=False,  # already in prompt template via {private_info}
    )

    response = await llm_client.chat(messages, temperature=0.3)

    threshold = state.get("evaluation_threshold", _DEFAULT_THRESHOLD)
    score = threshold
    feedback = ""

    try:
        json_str = response
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        parsed = json.loads(json_str.strip())
        score = float(parsed.get("score", threshold))
        feedback = parsed.get("feedback", "")
    except (json.JSONDecodeError, IndexError, ValueError):
        logger.warning("Failed to parse evaluator JSON output, defaulting to pass")
        score = threshold

    feedback_preview = feedback[:80] if feedback else ""
    logger.info("[%s] Evaluator → score=%.1f, feedback='%s'", player_id, score, feedback_preview)

    return {
        "evaluation_score": score,
        "evaluation_feedback": feedback,
        "retry_count": retry_count + 1,
    }


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


def _force_fix_action(state: AgentState) -> None:
    """Last-resort fix for invalid actions using tools_schema — fully game-agnostic.

    Fixes action_type if not in available_actions, then scans required fields:
    player-target fields get reassigned to the first valid alive player;
    empty text fields get a placeholder.
    """
    action_type = state.get("final_action_type", "")
    payload = state.get("final_action_payload", {})
    player_id = state.get("player_id", "")
    public_state = state.get("public_state", {})
    tools_schema = state.get("tools_schema", [])
    available_actions = state.get("available_actions", [])

    # Fix action_type if not in available_actions
    if available_actions and action_type not in available_actions:
        old_type = action_type
        action_type = available_actions[0]
        state["final_action_type"] = action_type
        logger.warning("[%s] Force-fixed action_type: '%s' → '%s'", player_id, old_type, action_type)
        # Rebuild payload for the corrected action type
        tool_def = _find_tool(tools_schema, action_type)
        if tool_def:
            params = tool_def.get("function", {}).get("parameters", {})
            required = params.get("required", [])
            new_payload = {}
            for field_name in required:
                new_payload[field_name] = payload.get(field_name, "")
            payload = new_payload
            state["final_action_payload"] = payload

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

        if _is_player_field(field_name, description):
            # Fix invalid player target
            if not value or value == player_id or (alive and value not in alive):
                if valid_targets:
                    old_value = value
                    payload[field_name] = valid_targets[0]
                    fixed = True
                    logger.warning("[%s] Force-fixed %s.%s: '%s' → '%s'",
                                   player_id, action_type, field_name, old_value, valid_targets[0])
        else:
            # Fix empty required text field
            if not value or not str(value).strip():
                payload[field_name] = "..."
                fixed = True
                logger.warning("[%s] Force-fixed %s.%s: empty → '...'",
                               player_id, action_type, field_name)

    if fixed:
        state["final_action_payload"] = payload
