"""LangGraph state definition for the player decision workflow."""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes.

    Input fields are set by PlayerAgent before graph invocation.
    Each node reads what it needs and writes its output fields.
    """

    # --- Input context (set by PlayerAgent) ---
    game_rules_prompt: str
    public_state: dict
    private_info: dict
    available_actions: list[str]
    tools_schema: list[dict]
    persona: str
    memory_context: list[dict]

    # --- Strategy prompts (injected from engine) ---
    thinker_prompt: str
    evaluator_prompt: str
    optimizer_prompt: str
    evaluation_threshold: float
    max_retries_limit: int

    # --- Thinker output ---
    situation_analysis: str
    strategy: str

    # --- Evaluator output ---
    evaluation_score: float
    evaluation_feedback: str
    retry_count: int

    # --- Optimizer output ---
    optimized_content: str
    expression: str

    # --- Final output ---
    final_action_type: str
    final_action_payload: dict
    full_thinking: str
