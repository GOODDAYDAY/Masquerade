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
        """Return information visible only to the specified player (NOT role)."""

    @abstractmethod
    def get_role_info(self, player_id: str) -> dict:
        """Return god-view info (role + word) for recording. NOT for agents."""

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
    def get_agent_strategy(self, player_id: str) -> AgentStrategy:
        """Return game-specific agent strategy for the given player.

        May vary by role — e.g. werewolf vs villager get different prompts.
        """

    # --- Optional overrides with default implementations ---

    def get_actionable_players(self) -> list[str]:
        """Return all players who can act right now.

        If multiple players are returned, the runner may process their
        LLM thinking in parallel (with concurrency control).
        Override in subclasses to enable concurrency for independent phases
        (e.g. voting where all players decide simultaneously).
        Default: wraps get_current_player() into a single-element list.
        """
        current = self.get_current_player()
        return [current] if current else []

    def format_action_log(self, player_id: str, action: Action) -> str:
        """Format an action for console logging. Override for game-specific formatting."""
        return "%s: %s" % (player_id, action.type)

    def get_broadcast_targets(self, player_id: str, action: Action) -> list[str] | None:
        """Which players should receive this action's public summary.

        Returns None = all players, [] = nobody, [ids] = specific players.
        """
        return None

    def format_public_summary(self, player_id: str, action: Action) -> str:
        """Format an action as a text summary for broadcasting to players' memory."""
        return "%s performed %s" % (player_id, action.type)

    def get_round_end_summary(self, round_number: int) -> str | None:
        """Return text summary to broadcast at end of round (e.g. vote results)."""
        return None

    def get_vote_result(self, round_number: int) -> dict | None:
        """Return vote result data for script recording.

        Expected format: {"votes": {voter: target}, "eliminated": str|None}.
        Returns None if no vote occurred this round.
        """
        return None
