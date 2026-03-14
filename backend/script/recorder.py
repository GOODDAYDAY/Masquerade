"""Game event recorder — observer that captures the full game timeline."""

import json
from datetime import datetime
from pathlib import Path

from backend.core.logging import get_logger
from backend.script.schema import (
    GameEvent,
    GameInfo,
    GameResult,
    GameScript,
    PlayerInfo,
    RoundData,
    VoteResult,
)

logger = get_logger("script.recorder")


class GameRecorder:
    """Records game events into a structured GameScript.

    Operates as a passive observer — recording failures do not affect game logic.
    """

    def __init__(self, game_info: GameInfo, players: list[PlayerInfo]) -> None:
        self.script = GameScript(game=game_info, players=players)
        self._current_round: RoundData | None = None
        self._start_time = datetime.now()
        logger.info("Recorder initialized for game type=%s", game_info.type)

    def start_round(self, round_number: int) -> None:
        """Begin recording a new round."""
        if self._current_round is not None:
            self.script.rounds.append(self._current_round)

        self._current_round = RoundData(round_number=round_number)
        logger.info("Recording round %d", round_number)

    def record_event(self, event: GameEvent) -> None:
        """Record a single game event in the current round."""
        if self._current_round is None:
            logger.warning("No active round, creating round 1")
            self.start_round(1)

        try:
            self._current_round.events.append(event)
        except Exception as e:
            logger.warning("Failed to record event: %s", e)

    def record_vote_result(self, result: VoteResult) -> None:
        """Record the voting outcome for the current round."""
        if self._current_round is None:
            logger.warning("No active round for vote result")
            return

        self._current_round.vote_result = result
        logger.info(
            "Vote result recorded: eliminated=%s",
            result.eliminated or "none (tie)",
        )

    def set_result(self, result: GameResult) -> None:
        """Set the final game result."""
        # Finalize the last round
        if self._current_round is not None:
            self.script.rounds.append(self._current_round)
            self._current_round = None

        elapsed = int((datetime.now() - self._start_time).total_seconds() * 1000)
        result.total_duration_ms = elapsed
        self.script.result = result
        logger.info("Game result set: winner=%s, duration=%dms", result.winner, elapsed)

    def export(self) -> GameScript:
        """Export the complete game script."""
        # Ensure last round is included
        if self._current_round is not None:
            self.script.rounds.append(self._current_round)
            self._current_round = None

        return self.script

    def save(self, output_dir: str) -> str:
        """Save the script to a JSON file and return the file path."""
        script = self.export()
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = script.game.created_at.strftime("%Y%m%d_%H%M%S")
        filename = "game_%s_%s.json" % (script.game.type, timestamp)
        file_path = output_path / filename

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(script.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

        logger.info("Script saved to %s", file_path)
        return str(file_path)
