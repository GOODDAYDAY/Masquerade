"""Abstract base class for all game engines."""

from abc import ABC, abstractmethod

from backend.agent.strategy import AgentStrategy
from backend.engine.models import Action, ActionResult, GameResult


class GameEngine(ABC):
    """Base class defining the contract for all game engines.

    Engine is a state machine — each apply_action call advances the game state.
    Engines are pure game logic, independent of LLM or any AI framework.
    """

    @abstractmethod
    def setup(self, players: list[str], config: dict) -> None:
        """Initialize the game, assign roles and resources."""

    @abstractmethod
    def get_player_ids(self) -> list[str]:
        """Return the list of player IDs in this game."""

    @abstractmethod
    def get_public_state(self) -> dict:
        """Return information visible to all players."""

    @abstractmethod
    def get_private_info(self, player_id: str) -> dict:
        """Return information visible only to the specified player."""

    @abstractmethod
    def get_available_actions(self, player_id: str) -> list[str]:
        """Return action types the player can currently perform."""

    @abstractmethod
    def apply_action(self, player_id: str, action: Action) -> ActionResult:
        """Execute an action and advance game state."""

    @abstractmethod
    def get_current_player(self) -> str | None:
        """Return the player_id whose turn it is, or None if N/A."""

    @abstractmethod
    def is_ended(self) -> bool:
        """Check whether the game has ended."""

    @abstractmethod
    def get_result(self) -> GameResult | None:
        """Return the game result, or None if still in progress."""

    @abstractmethod
    def get_game_rules_prompt(self) -> str:
        """Return the game rules as a prompt string for LLM agents."""

    @abstractmethod
    def get_tools_schema(self) -> list[dict]:
        """Return tool definitions for the current game phase."""

    @abstractmethod
    def get_agent_strategy(self) -> AgentStrategy:
        """Return game-specific agent strategy (prompt templates for decision nodes)."""
