"""PrivateOverlay — per-player private edges and derived inferences.

Thin layer on top of SharedGraph. Contains only information unique to
a single player: seer verification results, werewolf teammate knowledge,
and inferences derived from combining private knowledge with public facts.
"""

from backend.core.logging import get_logger
from backend.reasoning.models import (
    Conflict,
    ConflictSeverity,
    EdgeType,
    GraphEdge,
    ReasoningChain,
)
from backend.reasoning.shared_graph import SharedGraph

logger = get_logger("reasoning.private_overlay")


class PrivateOverlay:
    """Per-player private graph layer, overlaid on the shared public graph."""

    def __init__(self, player_id: str) -> None:
        self._player_id = player_id
        self._private_edges: list[GraphEdge] = []
        self._inferences: list[ReasoningChain] = []
        self._private_conflicts: list[Conflict] = []

        # Cached lookup structures
        self._known_wolves: set[str] = set()
        self._known_good: set[str] = set()
        self._teammates: set[str] = set()

    # ══════════════════════════════════════════════
    #  Public orchestration methods
    # ══════════════════════════════════════════════

    def add_private_edge(self, edge: GraphEdge) -> None:
        """Add a private edge and update lookup caches."""
        self._private_edges.append(edge)
        self._update_knowledge_cache(edge)

    def derive_inferences(self, shared: SharedGraph) -> None:
        """Derive private inferences from private knowledge + public graph."""
        self._inferences.clear()
        self._private_conflicts.clear()
        # Cross-reference private knowledge against public behavior
        self._infer_wolf_defenders(shared)      # Who defends a known wolf?
        self._infer_good_accusers(shared)        # Who accuses a known good player?
        self._infer_teammate_coordination(shared) # Is my teammate exposing us?
        self._detect_vote_against_known_good(shared)  # Who voted against verified good?
        self._detect_defense_of_known_wolf(shared)    # Who defended a verified wolf?
        logger.debug("[%s] Derived %d inferences, %d private conflicts",
                      self._player_id, len(self._inferences), len(self._private_conflicts))

    def get_private_conflicts(self) -> list[Conflict]:
        return list(self._private_conflicts)

    def get_private_edges(self) -> list[GraphEdge]:
        return list(self._private_edges)

    def get_inferences(self) -> list[ReasoningChain]:
        return list(self._inferences)

    def get_known_wolves(self) -> set[str]:
        return set(self._known_wolves)

    def get_known_good(self) -> set[str]:
        return set(self._known_good)

    def get_teammates(self) -> set[str]:
        return set(self._teammates)

    # ══════════════════════════════════════════════
    #  Private step methods
    # ══════════════════════════════════════════════

    def _update_knowledge_cache(self, edge: GraphEdge) -> None:
        """Update lookup sets based on edge type."""
        if edge.type == EdgeType.VERIFIED:
            result = edge.attrs.get("result", "")
            if result == "wolf":
                self._known_wolves.add(edge.target)
                logger.info("[%s] Learned: %s is wolf (verified)", self._player_id, edge.target)
            elif result == "good":
                self._known_good.add(edge.target)
                logger.info("[%s] Learned: %s is good (verified)", self._player_id, edge.target)
        elif edge.type == EdgeType.TEAMMATE:
            self._teammates.add(edge.target)
            logger.info("[%s] Learned: %s is teammate", self._player_id, edge.target)

    def _infer_wolf_defenders(self, shared: SharedGraph) -> None:
        """If someone defends a known wolf → they are suspicious."""
        if not self._known_wolves:
            return
        defense_edges = shared.get_edges_by_type(EdgeType.DEFENDS)
        for edge in defense_edges:
            defender = edge["source"]
            defended = edge["target"]
            if defended in self._known_wolves and defender != self._player_id:
                self._inferences.append(ReasoningChain(
                    premises=[
                        "我知道 %s 是狼人" % defended,
                        "%s 在 R%d 为 %s 辩护" % (defender, edge.get("round", 0), defended),
                    ],
                    conclusion="%s 帮狼人辩护，可能是狼队友" % defender,
                    confidence=0.7,
                    path=[defender, defended],
                ))

    def _infer_good_accusers(self, shared: SharedGraph) -> None:
        """If someone accuses a known-good player → they are suspicious."""
        if not self._known_good:
            return
        accuse_edges = shared.get_edges_by_type(EdgeType.ACCUSES)
        for edge in accuse_edges:
            accuser = edge["source"]
            accused = edge["target"]
            if accused in self._known_good and accuser != self._player_id:
                self._inferences.append(ReasoningChain(
                    premises=[
                        "我知道 %s 是好人" % accused,
                        "%s 在 R%d 指控 %s" % (accuser, edge.get("round", 0), accused),
                    ],
                    conclusion="%s 指控已知好人，可能是狼人" % accuser,
                    confidence=0.6,
                    path=[accuser, accused],
                ))

    def _infer_teammate_coordination(self, shared: SharedGraph) -> None:
        """For wolves: analyze if teammates' public behavior exposes the team."""
        if not self._teammates:
            return
        for teammate in self._teammates:
            edges = shared.get_edges_involving(teammate)
            defense_of_me = [
                e for e in edges
                if e.get("type") == EdgeType.DEFENDS and e["target"] == self._player_id
            ]
            if defense_of_me:
                self._inferences.append(ReasoningChain(
                    premises=[
                        "%s 是我的狼队友" % teammate,
                        "%s 公开为我辩护了" % teammate,
                    ],
                    conclusion="队友 %s 的辩护可能暴露我们的关系，需要注意" % teammate,
                    confidence=0.5,
                    path=[self._player_id, teammate],
                ))

    def _detect_vote_against_known_good(self, shared: SharedGraph) -> None:
        """Private conflict: someone voted against a player I know is good."""
        if not self._known_good:
            return
        vote_edges = shared.get_edges_by_type(EdgeType.VOTES_FOR)
        for edge in vote_edges:
            voter = edge["source"]
            target = edge["target"]
            if target in self._known_good and voter != self._player_id:
                self._private_conflicts.append(Conflict(
                    description="%s 在 R%d 投票给了已知好人 %s" % (
                        voter, edge.get("round", 0), target,
                    ),
                    severity=ConflictSeverity.MEDIUM,
                    involved_players=[voter, target],
                    round_detected=edge.get("round", 0),
                    evidence_type="vote_pattern",
                    evidence=[
                        "我验过 %s 是好人" % target,
                        "%s 投票要淘汰 %s" % (voter, target),
                    ],
                ))

    def _detect_defense_of_known_wolf(self, shared: SharedGraph) -> None:
        """Private conflict: someone defended a player I know is a wolf."""
        if not self._known_wolves:
            return
        defense_edges = shared.get_edges_by_type(EdgeType.DEFENDS)
        for edge in defense_edges:
            defender = edge["source"]
            defended = edge["target"]
            if defended in self._known_wolves and defender != self._player_id:
                self._private_conflicts.append(Conflict(
                    description="%s 在 R%d 为已知狼人 %s 辩护" % (
                        defender, edge.get("round", 0), defended,
                    ),
                    severity=ConflictSeverity.HIGH,
                    involved_players=[defender, defended],
                    round_detected=edge.get("round", 0),
                    evidence_type="speech_contradiction",
                    evidence=[
                        "我知道 %s 是狼人" % defended,
                        "%s 为 %s 辩护" % (defender, defended),
                    ],
                ))
