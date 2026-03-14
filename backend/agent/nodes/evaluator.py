"""Evaluator node — assesses the proposed strategy and decides if retry is needed.

Uses game-specific prompt and threshold from AgentStrategy (injected via state).
"""

import json

from backend.agent.llm_client import LLMClient
from backend.agent.state import AgentState
from backend.core.logging import get_logger

logger = get_logger("agent.nodes.evaluator")

_DEFAULT_THRESHOLD = 6.0
_DEFAULT_MAX_RETRIES = 2


async def evaluator_node(state: AgentState, llm_client: LLMClient) -> dict:
    """Evaluate the proposed strategy and score it using game-specific criteria."""
    prompt_template = state.get("evaluator_prompt", "")
    prompt = prompt_template.format(
        situation_analysis=state.get("situation_analysis", ""),
        strategy=state.get("strategy", ""),
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

    retry_count = state.get("retry_count", 0)
    logger.info("Evaluator: score=%.1f, retry_count=%d", score, retry_count)

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

    if score < threshold and retry_count <= max_retries:
        logger.info("Evaluator: score %.1f below threshold, retrying (attempt %d)", score, retry_count)
        return "retry"

    if retry_count > max_retries:
        logger.info("Evaluator: max retries reached, proceeding with current result")

    return "proceed"
