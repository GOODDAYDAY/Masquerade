"""Game Reasoning Graph (GRG) — structured reasoning for board game AI.

Public API: GameReasoningGraph facade class.
Runner only needs 4 methods: setup, update_round, get_thinker_context, get_evaluator_context.
"""

from backend.reasoning.cognitive_bias import apply_bias_to_conflicts, resolve_cognitive_bias
from backend.reasoning.conflict_detector import ConflictDetector
from backend.reasoning.extractor import EventExtractor
from backend.reasoning.models import CognitiveBias, GraphSummary
from backend.reasoning.private_overlay import PrivateOverlay
from backend.reasoning.reasoner import Reasoner
from backend.reasoning.shared_graph import SharedGraph
from backend.reasoning.summarizer import GraphSummarizer

from backend.core.logging import get_logger

logger = get_logger("reasoning.grg")


class GameReasoningGraph:
    """Facade: exposes a simple API, orchestrates all internal components.

    Runner calls:
    - setup(): once at game start
    - update_round(): once per round end
    - get_thinker_context(pid): per player decision
    - get_evaluator_context(pid): per player decision
    """

    def __init__(self) -> None:
        self._shared = SharedGraph()
        self._overlays: dict[str, PrivateOverlay] = {}
        self._biases: dict[str, CognitiveBias] = {}
        self._extractor = EventExtractor()
        self._conflict_detector = ConflictDetector()
        self._reasoner = Reasoner()
        self._summarizer = GraphSummarizer()
        self._round_actions: list[dict] = []
        logger.debug("GameReasoningGraph initialized")

    # ══════════════════════════════════════════════
    #  Public orchestration methods
    # ══════════════════════════════════════════════

    def setup(self, player_ids: list[str], personas: dict[str, str]) -> None:
        """Initialize overlays and cognitive biases for all players."""
        for pid in player_ids:
            self._overlays[pid] = PrivateOverlay(pid)
            self._biases[pid] = resolve_cognitive_bias(personas.get(pid, ""))
        logger.info(
            "GRG setup: %d players, biases resolved",
            len(player_ids),
        )

    def record_action(self, player_id: str, action_type: str, payload: dict) -> None:
        """Record an action for later extraction. Called after each apply_action."""
        self._round_actions.append({
            "player_id": player_id,
            "type": action_type,
            "payload": payload,
        })

    def update_round(self, round_number: int, public_state: dict) -> None:
        """Extract events, update shared graph, reset round buffer. Called once per round end."""
        public_edges = self._extractor.extract_round_events(
            round_number, public_state, self._round_actions,
        )
        self._shared.update(round_number, public_edges)
        self._round_actions.clear()
        logger.info(
            "GRG round %d updated: %d public edges, %d conflicts detected",
            round_number, len(public_edges), len(self._shared.get_public_conflicts()),
        )

    def update_private(
        self, player_id: str, round_number: int, private_info: dict,
    ) -> None:
        """Update a player's private overlay with their private info."""
        overlay = self._overlays.get(player_id)
        if not overlay:
            return

        private_edges = self._extractor.extract_private_events(
            player_id, round_number, private_info,
        )
        for edge in private_edges:
            overlay.add_private_edge(edge)

        if private_edges:
            overlay.derive_inferences(self._shared)
            logger.debug(
                "GRG private update: %s got %d private edges",
                player_id, len(private_edges),
            )

    def get_thinker_context(self, player_id: str, alive_players: list[str]) -> str:
        """Get graph reasoning summary text for Thinker prompt injection."""
        overlay = self._overlays.get(player_id)
        bias = self._biases.get(player_id)
        if not overlay or not bias:
            return ""

        trust, suspicion, chains = self._run_reasoning(player_id, overlay, bias, alive_players)
        conflicts = self._collect_all_conflicts(player_id, overlay, bias)
        summary = self._build_summary(trust, suspicion, conflicts, chains, bias)
        return self._summarizer.to_thinker_text(summary)

    def get_evaluator_context(self, player_id: str) -> str:
        """Get conflict list text for Evaluator prompt injection."""
        overlay = self._overlays.get(player_id)
        bias = self._biases.get(player_id)
        if not overlay or not bias:
            return ""

        conflicts = self._collect_all_conflicts(player_id, overlay, bias)
        return self._summarizer.to_evaluator_text(conflicts)

    # ══════════════════════════════════════════════
    #  Private step methods
    # ══════════════════════════════════════════════

    def _run_reasoning(
        self,
        player_id: str,
        overlay: PrivateOverlay,
        bias: CognitiveBias,
        alive_players: list[str],
    ) -> tuple[dict[str, float], dict[str, float], list]:
        """Run the reasoner to get trust, suspicion, and chains."""
        return self._reasoner.reason(
            player_id, self._shared, overlay, bias, alive_players,
        )

    def _collect_all_conflicts(
        self, player_id: str, overlay: PrivateOverlay, bias: CognitiveBias,
    ) -> list:
        """Merge public + private conflicts and apply bias sorting."""
        public = self._conflict_detector.detect_public(self._shared)
        private = self._conflict_detector.detect_private(
            self._shared, overlay, self._shared._current_round,
        )
        return apply_bias_to_conflicts(public + private, bias)

    def _build_summary(
        self,
        trust: dict[str, float],
        suspicion: dict[str, float],
        conflicts: list,
        chains: list,
        bias: CognitiveBias,
    ) -> GraphSummary:
        """Build the final summary from all reasoning outputs."""
        return self._summarizer.summarize(
            self._shared, trust, suspicion, conflicts, chains, bias,
        )


__all__ = ["GameReasoningGraph"]
