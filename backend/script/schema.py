"""Pydantic models defining the game script data structure.

This is the cross-pipeline data contract — used by orchestrator, API,
and future renderer/frontend modules.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from backend.engine.models import Action


class MemorySnapshot(BaseModel):
    """Snapshot of a player's memory at event time."""

    private: list[str] = Field(default_factory=list)
    public: list[str] = Field(default_factory=list)


class GameEvent(BaseModel):
    """A single event in the game timeline."""

    player_id: str
    phase: str
    timestamp: datetime = Field(default_factory=datetime.now)
    thinking_duration_ms: int = 0
    thinking: str = ""
    expression: str = "neutral"
    action: Action
    strategy_tip: str = ""
    memory_snapshot: MemorySnapshot = Field(default_factory=MemorySnapshot)


class VoteResult(BaseModel):
    """Result of a voting round."""

    votes: dict[str, str] = Field(default_factory=dict)
    eliminated: str | None = None


class RoundData(BaseModel):
    """Data for a single game round."""

    round_number: int
    events: list[GameEvent] = Field(default_factory=list)
    vote_result: VoteResult | None = None


class GameInfo(BaseModel):
    """Metadata about the game session."""

    type: str
    config: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)


class PlayerInfo(BaseModel):
    """Player information recorded in the script."""

    id: str
    name: str
    model: str = ""
    persona: str = ""
    appearance: str = ""
    role: str = ""
    word: str = ""
    extra: dict = Field(default_factory=dict)  # Game-specific data from engine


class GameResult(BaseModel):
    """Final game outcome."""

    winner: str
    eliminated_order: list[str] = Field(default_factory=list)
    total_rounds: int = 0
    total_duration_ms: int = 0


class GameScript(BaseModel):
    """Top-level script structure containing the full game record."""

    game: GameInfo
    players: list[PlayerInfo] = Field(default_factory=list)
    rounds: list[RoundData] = Field(default_factory=list)
    result: GameResult | None = None
