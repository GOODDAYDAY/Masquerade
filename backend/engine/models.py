"""Data models shared across all game engines."""

from pydantic import BaseModel


class Action(BaseModel):
    """A player action submitted to the engine."""

    type: str
    player_id: str
    payload: dict


class ActionResult(BaseModel):
    """Result returned after applying an action."""

    success: bool
    message: str
    public_info: dict | None = None


class GameResult(BaseModel):
    """Final result of a completed game."""

    winner: str
    eliminated_order: list[str]
    total_rounds: int


class PlayerState(BaseModel):
    """Tracked state for a single player within the engine."""

    player_id: str
    alive: bool = True
    role: str = ""
    word: str = ""
