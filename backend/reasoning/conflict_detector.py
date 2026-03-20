"""ConflictDetector — scans graph for logical contradictions.

Public conflicts are detected once per round and cached in SharedGraph.
Private conflicts are detected per-player using their PrivateOverlay.
This class provides the orchestration; the actual detection logic
lives in SharedGraph (public) and PrivateOverlay (private).
"""

from backend.reasoning.models import Conflict
from backend.reasoning.private_overlay import PrivateOverlay
from backend.reasoning.shared_graph import SharedGraph


class ConflictDetector:
    """Orchestrates conflict detection across public and private layers."""

    # ══════════════════════════════════════════════
    #  Public orchestration methods
    # ══════════════════════════════════════════════

    def detect_public(self, shared: SharedGraph) -> list[Conflict]:
        """Return cached public conflicts (already computed during SharedGraph.update)."""
        return shared.get_public_conflicts()

    def detect_private(
        self,
        shared: SharedGraph,
        overlay: PrivateOverlay,
        round_number: int,
    ) -> list[Conflict]:
        """Detect private conflicts based on player's private knowledge.

        Triggers re-derivation of inferences and conflicts from
        the overlay's private edges against the shared graph.
        """
        overlay.derive_inferences(shared)
        return overlay.get_private_conflicts()
