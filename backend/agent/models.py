"""Data models for the agent layer."""

from pydantic import BaseModel

from backend.engine.models import Action


class AgentResponse(BaseModel):
    """Final output from a player agent's decision process."""

    thinking: str
    action: Action
    expression: str = "neutral"
    thinking_duration_ms: int = 0
    strategy_tip: str = ""
