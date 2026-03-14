"""Evaluator node — assesses the proposed strategy and decides if retry is needed.

Two-layer evaluation:
  1. Programmatic validation — checks action legality (vote target valid, speech not empty, etc.)
  2. LLM scoring — uses game-specific prompt to evaluate strategy quality

If programmatic validation fails, skip LLM call and return score=0 with clear feedback.
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.evaluator")

_DEFAULT_THRESHOLD = 6.0
_DEFAULT_MAX_RETRIES = 2


def _validate_action(state: AgentState) -> str | None:
    """Programmatic validation of the proposed action.

    Returns None if valid, or an error message string if invalid.
    """
    action_type = state.get("final_action_type", "")
    payload = state.get("final_action_payload", {})
    player_id = state.get("player_id", "")
    public_state = state.get("public_state", {})
    available_actions = state.get("available_actions", [])

    # Check action type is available
    if action_type not in available_actions:
        return "action_type '%s' is not available. Available actions: %s" % (action_type, available_actions)

    if action_type == "speak":
        content = payload.get("content", "")
        if not content or not content.strip():
            return "Speech content is empty. You must say something."

    elif action_type == "vote":
        target = payload.get("target_player_id", "")
        if not target:
            return "Vote target is empty. You must vote for a player."

        # Cannot vote for yourself
        if target == player_id:
            alive_players = public_state.get("alive_players", [])
            valid_targets = [p for p in alive_players if p != player_id]
            return (
                "You voted for yourself ('%s'). This is not allowed. "
                "You must vote for another player. Valid targets: %s"
                % (target, valid_targets)
            )

        # Target must be alive
        alive_players = public_state.get("alive_players", [])
        if alive_players and target not in alive_players:
            valid_targets = [p for p in alive_players if p != player_id]
            return (
                "Vote target '%s' is not alive or does not exist. "
                "Valid targets: %s" % (target, valid_targets)
            )

    return None


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

    # Layer 2: LLM scoring
    prompt_template = state.get("evaluator_prompt", "")
    situation_analysis = state.get("situation_analysis", "")
    strategy = state.get("strategy", "")

    prompt = prompt_template.format(
        situation_analysis=json.dumps(situation_analysis, ensure_ascii=False) if isinstance(situation_analysis, dict) else str(situation_analysis),
        strategy=json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy),
        action_type=state.get("final_action_type", ""),
        action_payload=json.dumps(state.get("final_action_payload", {}), ensure_ascii=False),
    )

    messages = [{"role": "user", "content": prompt}]
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
        # Force-fix obvious violations before proceeding
        _force_fix_action(state)
    else:
        logger.info("[%s] Evaluator: PASSED → proceeding to Optimizer", player_id)

    return "proceed"


def _force_fix_action(state: AgentState) -> None:
    """Last-resort fix for invalid actions when max retries are exhausted."""
    action_type = state.get("final_action_type", "")
    payload = state.get("final_action_payload", {})
    player_id = state.get("player_id", "")
    public_state = state.get("public_state", {})

    if action_type == "vote":
        target = payload.get("target_player_id", "")
        alive = public_state.get("alive_players", [])
        valid_targets = [p for p in alive if p != player_id]

        if target == player_id or target not in alive:
            if valid_targets:
                new_target = valid_targets[0]
                payload["target_player_id"] = new_target
                state["final_action_payload"] = payload
                logger.warning("[%s] Force-fixed vote: '%s' → '%s'",
                               player_id, target, new_target)
