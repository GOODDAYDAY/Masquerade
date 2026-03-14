"""AgentStrategy — game-specific prompt templates injected into generic agent nodes.

Each game engine provides its own strategy via get_agent_strategy().
The agent framework uses these prompts without knowing game-specific details.
"""

from pydantic import BaseModel


class AgentStrategy(BaseModel):
    """Container for game-specific prompt templates used by agent nodes."""

    thinker_prompt: str
    evaluator_prompt: str
    optimizer_prompt: str
    evaluation_threshold: float = 6.0
    max_retries: int = 2
