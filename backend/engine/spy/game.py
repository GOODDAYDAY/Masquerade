"""Spy game (Who Is The Spy) engine implementation."""

import random
from enum import Enum

from backend.core.exceptions import IllegalActionError
from backend.core.logging import get_logger
from backend.engine.base import GameEngine
from backend.engine.models import Action, ActionResult, GameResult, PlayerState
from backend.engine.registry import register_game
from backend.agent.strategy import AgentStrategy
from backend.engine.spy.prompts import get_rules_prompt
from backend.engine.spy.strategy import get_spy_strategy, get_blank_strategy
from backend.engine.spy.words import DEFAULT_WORD_PAIRS

logger = get_logger("engine.spy")

_MIN_PLAYERS = 3


class GamePhase(str, Enum):
    WAITING = "waiting"
    SPEAKING = "speaking"
    VOTING = "voting"
    ELIMINATING = "eliminating"
    ENDED = "ended"


@register_game("spy")
class SpyGame(GameEngine):
    """State machine implementation of Who Is The Spy."""

    _MAX_CONSECUTIVE_TIES = 3

    def __init__(self) -> None:
        self.phase: GamePhase = GamePhase.WAITING
        self.players: dict[str, PlayerState] = {}
        self.player_order: list[str] = []
        self.current_player_idx: int = 0
        self.round_number: int = 0
        self.spy_count: int = 1
        self.blank_count: int = 0
        self.word_pair: tuple[str, str] = ("", "")
        self.votes: dict[str, str] = {}
        self.speeches: dict[int, list[dict]] = {}  # round -> [{player_id, content}]
        self.eliminated_order: list[str] = []
        self.vote_history: dict[int, dict[str, str]] = {}  # round -> {voter: target}
        self.consecutive_ties: int = 0

    def setup(self, players: list[str], config: dict) -> None:
        if len(players) < _MIN_PLAYERS:
            raise IllegalActionError(
                "Spy game requires at least %d players, got %d" % (_MIN_PLAYERS, len(players))
            )

        self.player_order = list(players)
        random.shuffle(self.player_order)
        self.spy_count = config.get("spy_count", 0)
        self.blank_count = config.get("blank_count", 0)
        total_special = self.spy_count + self.blank_count

        if total_special > len(players):
            raise IllegalActionError(
                "spy_count(%d) + blank_count(%d) exceeds player count(%d)"
                % (self.spy_count, self.blank_count, len(players))
            )

        # Pick a random word pair (used by civilians and spies)
        word_pairs = config.get("word_pairs", DEFAULT_WORD_PAIRS)
        civilian_word, spy_word = random.choice(word_pairs)
        self.word_pair = (civilian_word, spy_word)

        # Assign roles randomly: spy, then blank, rest civilian
        special_indices = random.sample(range(len(players)), total_special) if total_special > 0 else []
        spy_indices = set(special_indices[:self.spy_count])
        blank_indices = set(special_indices[self.spy_count:])

        for i, pid in enumerate(players):
            if i in spy_indices:
                role, word = "spy", spy_word
            elif i in blank_indices:
                role, word = "blank", ""
            else:
                role, word = "civilian", civilian_word
            self.players[pid] = PlayerState(
                player_id=pid, alive=True, role=role, word=word,
            )

        logger.info(
            "Game setup: %d players, %d spies, %d blanks, words=(%s/%s)",
            len(players), self.spy_count, self.blank_count,
            civilian_word, spy_word,
        )

        self.round_number = 1
        self.current_player_idx = 0
        self.phase = GamePhase.SPEAKING
        self.speeches[self.round_number] = []

    def get_player_ids(self) -> list[str]:
        return list(self.player_order)

    def get_public_state(self) -> dict:
        alive = [pid for pid, ps in self.players.items() if ps.alive]
        return {
            "phase": self.phase.value,
            "round_number": self.round_number,
            "alive_players": alive,
            "eliminated_players": self.eliminated_order,
            "speeches": self.speeches,
            "vote_history": self.vote_history,
            "current_player": self.get_current_player(),
        }

    def get_private_info(self, player_id: str) -> dict:
        """Info visible to the player — only their word, NOT their role."""
        ps = self.players.get(player_id)
        if not ps:
            return {}
        if ps.role == "blank":
            return {"word": "", "is_blank": True}
        return {"word": ps.word}

    def get_role_info(self, player_id: str) -> dict:
        """God-view info for recording — includes role. NOT for agents."""
        ps = self.players.get(player_id)
        if not ps:
            return {}
        return {
            "role": ps.role,
            "word": ps.word,
        }

    def get_available_actions(self, player_id: str) -> list[str]:
        ps = self.players.get(player_id)
        if not ps or not ps.alive:
            return []

        if self.phase == GamePhase.SPEAKING and self.get_current_player() == player_id:
            return ["speak"]
        if self.phase == GamePhase.VOTING and player_id not in self.votes:
            return ["vote"]
        return []

    def apply_action(self, player_id: str, action: Action) -> ActionResult:
        ps = self.players.get(player_id)
        if not ps or not ps.alive:
            raise IllegalActionError("Player %s is not alive or does not exist" % player_id)

        if action.type == "speak":
            return self._handle_speak(player_id, action)
        if action.type == "vote":
            return self._handle_vote(player_id, action)

        raise IllegalActionError("Unknown action type: %s" % action.type)

    def get_current_player(self) -> str | None:
        if self.phase == GamePhase.SPEAKING:
            alive_order = [pid for pid in self.player_order if self.players[pid].alive]
            if self.current_player_idx < len(alive_order):
                return alive_order[self.current_player_idx]
        if self.phase == GamePhase.VOTING:
            # All alive players who haven't voted yet
            alive_order = [pid for pid in self.player_order if self.players[pid].alive]
            for pid in alive_order:
                if pid not in self.votes:
                    return pid
        return None

    def is_ended(self) -> bool:
        return self.phase == GamePhase.ENDED

    def get_result(self) -> GameResult | None:
        if not self.is_ended():
            return None

        alive = [pid for pid in self.player_order if self.players[pid].alive]
        alive_spies = [pid for pid in alive if self.players[pid].role == "spy"]
        alive_blanks = [pid for pid in alive if self.players[pid].role == "blank"]

        if not alive_spies and not alive_blanks:
            winner = "civilian"
        else:
            winners = []
            if alive_spies:
                winners.append("spy")
            if alive_blanks:
                winners.append("blank")
            winner = ",".join(winners)

        return GameResult(
            winner=winner,
            eliminated_order=self.eliminated_order,
            total_rounds=self.round_number,
        )

    def get_game_rules_prompt(self) -> str:
        return get_rules_prompt("standard", self.blank_count > 0)

    def get_tools_schema(self) -> list[dict]:
        if self.phase == GamePhase.SPEAKING:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "speak",
                        "description": "发言描述你拿到的词，注意不要太直接暴露",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "你的发言内容",
                                }
                            },
                            "required": ["content"],
                        },
                    },
                }
            ]
        if self.phase == GamePhase.VOTING:
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "vote",
                        "description": "投票选择你认为是卧底的玩家",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "target_player_id": {
                                    "type": "string",
                                    "description": "你要投票的玩家ID",
                                }
                            },
                            "required": ["target_player_id"],
                        },
                    },
                }
            ]
        return []

    def get_agent_strategy(self, player_id: str) -> AgentStrategy:
        ps = self.players.get(player_id)
        if ps and ps.role == "blank":
            return get_blank_strategy()
        return get_spy_strategy()

    def get_actionable_players(self) -> list[str]:
        if self.phase == GamePhase.VOTING:
            # All unvoted alive players can think in parallel
            return [pid for pid in self.player_order
                    if self.players[pid].alive and pid not in self.votes]
        current = self.get_current_player()
        return [current] if current else []

    def format_action_log(self, player_id: str, action: Action) -> str:
        if action.type == "speak":
            return "[%s] %s says: %s" % (self.phase.value, player_id, action.payload.get("content", ""))
        if action.type == "vote":
            return "[%s] %s votes for: %s" % (self.phase.value, player_id, action.payload.get("target_player_id", ""))
        return "%s: %s" % (player_id, action.type)

    def get_broadcast_targets(self, player_id: str, action: Action) -> list[str] | None:
        if action.type == "vote":
            return []  # secret ballot
        return None  # broadcast to all

    def format_public_summary(self, player_id: str, action: Action) -> str:
        if action.type == "speak":
            return "%s 说: %s" % (player_id, action.payload.get("content", ""))
        return "%s 执行了 %s" % (player_id, action.type)

    def get_round_end_summary(self, round_number: int) -> str | None:
        votes = self.vote_history.get(round_number, {})
        if not votes:
            return None
        vote_lines = ["%s \u2192 %s" % (voter, target) for voter, target in votes.items()]
        # Find who was eliminated this round
        eliminated = self._get_eliminated_in_round(round_number)
        if eliminated:
            return "\u6295\u7968\u8be6\u60c5: %s\n\u7ed3\u679c: %s \u88ab\u6dd8\u6c70" % (
                ", ".join(vote_lines), eliminated)
        return "\u6295\u7968\u8be6\u60c5: %s\n\u7ed3\u679c: \u5e73\u7968\uff0c\u65e0\u4eba\u6dd8\u6c70" % ", ".join(vote_lines)

    def get_vote_result(self, round_number: int) -> dict | None:
        votes = self.vote_history.get(round_number, {})
        if not votes:
            return None
        eliminated = self._get_eliminated_in_round(round_number)
        return {"votes": votes, "eliminated": eliminated}

    def _get_eliminated_in_round(self, round_number: int) -> str | None:
        """Find who was eliminated in a specific round by checking elimination order."""
        # Count eliminations up to this round vs previous rounds
        rounds_before = [r for r in sorted(self.vote_history.keys()) if r < round_number]
        elim_before = 0
        for r in rounds_before:
            v = self.vote_history[r]
            counts: dict[str, int] = {}
            for t in v.values():
                counts[t] = counts.get(t, 0) + 1
            if counts:
                max_c = max(counts.values())
                top = [p for p, c in counts.items() if c == max_c]
                if len(top) == 1:
                    elim_before += 1
        if elim_before < len(self.eliminated_order):
            return self.eliminated_order[elim_before]
        return None

    # --- Internal handlers ---

    def _handle_speak(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != GamePhase.SPEAKING:
            raise IllegalActionError("Not in speaking phase")
        if self.get_current_player() != player_id:
            raise IllegalActionError("Not %s's turn to speak" % player_id)

        content = action.payload.get("content", "")
        if not content:
            raise IllegalActionError("Speech content cannot be empty")

        self.speeches[self.round_number].append({
            "player_id": player_id,
            "content": content,
        })
        logger.info("Round %d: %s spoke", self.round_number, player_id)

        # Advance to next alive player
        alive_order = [pid for pid in self.player_order if self.players[pid].alive]
        self.current_player_idx += 1

        # All players have spoken → move to voting
        if self.current_player_idx >= len(alive_order):
            self.phase = GamePhase.VOTING
            self.votes = {}
            logger.info("Round %d: speaking phase complete, entering voting", self.round_number)

        return ActionResult(
            success=True,
            message="Speech recorded",
            public_info={"player_id": player_id, "content": content},
        )

    def _handle_vote(self, player_id: str, action: Action) -> ActionResult:
        if self.phase != GamePhase.VOTING:
            raise IllegalActionError("Not in voting phase")
        if player_id in self.votes:
            raise IllegalActionError("Player %s has already voted" % player_id)

        target = action.payload.get("target_player_id", "")
        if target not in self.players or not self.players[target].alive:
            raise IllegalActionError("Invalid vote target: %s" % target)
        if target == player_id:
            raise IllegalActionError("Cannot vote for yourself")

        self.votes[player_id] = target
        logger.info("Round %d: %s voted for %s", self.round_number, player_id, target)

        # Check if all alive players have voted
        alive = [pid for pid in self.player_order if self.players[pid].alive]
        if len(self.votes) >= len(alive):
            return self._resolve_votes()

        return ActionResult(
            success=True,
            message="Vote recorded",
            public_info={"player_id": player_id, "voted": True},
        )

    def _resolve_votes(self) -> ActionResult:
        """Count votes, eliminate the top-voted player or handle ties."""
        # Record vote history (public information)
        self.vote_history[self.round_number] = dict(self.votes)

        vote_counts: dict[str, int] = {}
        for target in self.votes.values():
            vote_counts[target] = vote_counts.get(target, 0) + 1

        max_votes = max(vote_counts.values())
        top_voted = [pid for pid, count in vote_counts.items() if count == max_votes]

        if len(top_voted) == 1:
            eliminated = top_voted[0]
            self.players[eliminated].alive = False
            self.eliminated_order.append(eliminated)
            self.consecutive_ties = 0
            logger.info(
                "Round %d: %s eliminated with %d votes",
                self.round_number, eliminated, max_votes,
            )
            result_info = {
                "vote_counts": vote_counts,
                "votes_detail": dict(self.votes),
                "eliminated": eliminated,
            }
        else:
            eliminated = None
            self.consecutive_ties += 1
            logger.info("Round %d: tie vote (%d consecutive), no elimination",
                        self.round_number, self.consecutive_ties)
            result_info = {
                "vote_counts": vote_counts,
                "votes_detail": dict(self.votes),
                "eliminated": None,
                "consecutive_ties": self.consecutive_ties,
            }

        # Check win condition (includes consecutive tie rule)
        if self._check_win_condition():
            self.phase = GamePhase.ENDED
            logger.info("Game ended after round %d", self.round_number)
        else:
            # Start next round
            self.round_number += 1
            self.current_player_idx = 0
            self.phase = GamePhase.SPEAKING
            self.speeches[self.round_number] = []
            self.votes = {}

        return ActionResult(
            success=True,
            message="Votes resolved" + (", %s eliminated" % eliminated if eliminated else ", tie"),
            public_info=result_info,
        )

    def _check_win_condition(self) -> bool:
        """Return True if the game should end."""
        alive = [pid for pid in self.player_order if self.players[pid].alive]
        alive_spies = [pid for pid in alive if self.players[pid].role == "spy"]
        alive_blanks = [pid for pid in alive if self.players[pid].role == "blank"]

        # All non-civilian roles eliminated → civilians win
        if not alive_spies and not alive_blanks:
            return True
        # Down to final 2 → non-civilian roles win
        if len(alive) <= 2:
            return True
        # Consecutive ties → non-civilian roles win
        if self.consecutive_ties >= self._MAX_CONSECUTIVE_TIES:
            logger.info("Game ended: %d consecutive ties, non-civilian roles win by deadlock",
                        self.consecutive_ties)
            return True
        return False
