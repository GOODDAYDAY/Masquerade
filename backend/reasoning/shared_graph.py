"""SharedGraph — the single source of truth for public game events.

Maintains a global graph of all publicly visible facts and relationships.
All analysis results (conflicts, clusters, vote alignment) are cached
after each round update, so N players can read them at zero cost.
"""

import networkx as nx

from backend.core.logging import get_logger
from backend.reasoning.models import (
    Conflict,
    ConflictSeverity,
    EdgeType,
    GraphEdge,
    NodeType,
)

logger = get_logger("reasoning.shared_graph")


class SharedGraph:
    """Public graph layer: stores all publicly observable facts and relations."""

    def __init__(self) -> None:
        self._graph = nx.MultiDiGraph()
        self._current_round: int = 0

        # Cached analysis results (refreshed once per round)
        self._public_conflicts: list[Conflict] = []
        self._vote_alignment: dict[tuple[str, str], int] = {}
        self._faction_clusters: dict[str, list[str]] = {}
        self._public_summary_text: str = ""

    # ══════════════════════════════════════════════
    #  Public orchestration methods
    # ══════════════════════════════════════════════

    def update(self, round_number: int, edges: list[GraphEdge]) -> None:
        """Write new edges and refresh all cached analysis. Called once per round."""
        self._current_round = round_number
        # 1. Write new relation edges into the graph
        self._add_edges(edges)
        # 2. Refresh all cached analysis (conflicts, alignment, clusters, summary)
        self._refresh_public_analysis(round_number)
        logger.info("SharedGraph updated: round=%d, total_nodes=%d, total_edges=%d",
                     round_number, self._graph.number_of_nodes(), self._graph.number_of_edges())

    def get_public_conflicts(self) -> list[Conflict]:
        return list(self._public_conflicts)

    def get_faction_clusters(self) -> dict[str, list[str]]:
        return dict(self._faction_clusters)

    def get_public_summary_text(self) -> str:
        return self._public_summary_text

    def get_vote_alignment(self) -> dict[tuple[str, str], int]:
        return dict(self._vote_alignment)

    def get_player_nodes(self) -> list[str]:
        """Return all player node IDs."""
        return [
            n for n, d in self._graph.nodes(data=True)
            if d.get("type") == NodeType.PLAYER
        ]

    def get_edges_by_type(self, edge_type: EdgeType) -> list[dict]:
        """Return all edges of a given type with their attributes."""
        results = []
        for u, v, data in self._graph.edges(data=True):
            if data.get("type") == edge_type:
                results.append({"source": u, "target": v, **data})
        return results

    def get_edges_involving(self, player_id: str) -> list[dict]:
        """Return all edges where the player is source or target."""
        results = []
        for u, v, data in self._graph.edges(data=True):
            if u == player_id or v == player_id:
                results.append({"source": u, "target": v, **data})
        return results

    # ══════════════════════════════════════════════
    #  Private step methods
    # ══════════════════════════════════════════════

    def _add_edges(self, edges: list[GraphEdge]) -> None:
        """Write new edges into the underlying graph."""
        for edge in edges:
            self._ensure_player_node(edge.source)
            self._ensure_player_node(edge.target)
            self._graph.add_edge(
                edge.source, edge.target,
                type=edge.type,
                round=edge.round,
                weight=edge.weight,
                **edge.attrs,
            )

    def _ensure_player_node(self, node_id: str) -> None:
        """Add a player node if it doesn't exist yet."""
        if not self._graph.has_node(node_id):
            self._graph.add_node(node_id, type=NodeType.PLAYER)

    def _refresh_public_analysis(self, round_number: int) -> None:
        """Refresh all public analysis caches (orchestration method)."""
        # 1. Scan for contradictions (speech-vote, role claims, attitude flips)
        self._detect_public_conflicts(round_number)
        # 2. Compute pairwise vote alignment matrix
        self._compute_vote_alignment()
        # 3. Cluster players into suspected factions
        self._compute_faction_clusters()
        # 4. Generate human-readable summary text
        self._generate_public_summary()

    def _detect_public_conflicts(self, round_number: int) -> None:
        """Scan graph for public contradictions."""
        conflicts: list[Conflict] = []
        # Check: did anyone accuse X but vote for Y?
        conflicts.extend(self._find_vote_speech_contradictions(round_number))
        # Check: did multiple players claim the same unique role?
        conflicts.extend(self._find_role_claim_conflicts())
        # Check: did anyone flip from accusing to defending the same person?
        conflicts.extend(self._find_attitude_flips(round_number))
        self._public_conflicts = conflicts
        logger.debug("Conflict detection: %d conflicts found in round %d",
                      len(conflicts), round_number)

    def _find_vote_speech_contradictions(self, round_number: int) -> list[Conflict]:
        """Detect speech-vote contradictions: accused X but voted for Y."""
        contradictions: list[Conflict] = []
        votes_this_round = self._get_edges_in_round(EdgeType.VOTES_FOR, round_number)
        accuses_this_round = self._get_edges_in_round(EdgeType.ACCUSES, round_number)

        accuser_targets: dict[str, list[str]] = {}
        for edge in accuses_this_round:
            accuser_targets.setdefault(edge["source"], []).append(edge["target"])

        for vote in votes_this_round:
            voter = vote["source"]
            vote_target = vote["target"]
            accused = accuser_targets.get(voter, [])
            if accused and vote_target not in accused:
                contradictions.append(Conflict(
                    description="R%d: %s 口头指控 %s，但投票给了 %s" % (
                        round_number, voter, "/".join(accused), vote_target,
                    ),
                    severity=ConflictSeverity.MEDIUM,
                    involved_players=[voter],
                    round_detected=round_number,
                    evidence_type="speech_contradiction",
                    evidence=[
                        "%s 指控了 %s" % (voter, "/".join(accused)),
                        "%s 投票给了 %s" % (voter, vote_target),
                    ],
                ))
        return contradictions

    def _find_role_claim_conflicts(self) -> list[Conflict]:
        """Detect role constraint violations: multiple players claiming a unique role."""
        role_claims: dict[str, list[tuple[str, int]]] = {}
        for u, v, data in self._graph.edges(data=True):
            if data.get("type") == EdgeType.CLAIMS_ROLE:
                role = v
                role_claims.setdefault(role, []).append((u, data.get("round", 0)))

        conflicts: list[Conflict] = []
        for role, claimants in role_claims.items():
            if len(claimants) > 1:
                players = [c[0] for c in claimants]
                latest_round = max(c[1] for c in claimants)
                conflicts.append(Conflict(
                    description="%s 都声称自己是%s，至少有一个是假的" % (
                        "、".join(players), role,
                    ),
                    severity=ConflictSeverity.HIGH,
                    involved_players=players,
                    round_detected=latest_round,
                    evidence_type="role_claim_conflict",
                    evidence=["%s 在 R%d 声称是%s" % (p, r, role) for p, r in claimants],
                ))
        return conflicts

    def _find_attitude_flips(self, round_number: int) -> list[Conflict]:
        """Detect attitude flips: accused X in round N, defended X in round M."""
        if round_number < 2:
            return []

        flips: list[Conflict] = []
        players = self.get_player_nodes()
        for player in players:
            accused_targets = set()
            defended_targets = set()
            for u, v, data in self._graph.edges(data=True):
                if u != player:
                    continue
                if data.get("type") == EdgeType.ACCUSES:
                    accused_targets.add(v)
                elif data.get("type") == EdgeType.DEFENDS:
                    defended_targets.add(v)

            flipped = accused_targets & defended_targets
            for target in flipped:
                accuse_rounds = self._get_rounds_for_edge(player, target, EdgeType.ACCUSES)
                defend_rounds = self._get_rounds_for_edge(player, target, EdgeType.DEFENDS)
                flips.append(Conflict(
                    description="%s 在 R%s 指控 %s，又在 R%s 为其辩护" % (
                        player,
                        "/".join(str(r) for r in sorted(accuse_rounds)),
                        target,
                        "/".join(str(r) for r in sorted(defend_rounds)),
                    ),
                    severity=ConflictSeverity.MEDIUM,
                    involved_players=[player, target],
                    round_detected=round_number,
                    evidence_type="attitude_flip",
                ))
        return flips

    def _compute_vote_alignment(self) -> None:
        """Compute vote alignment matrix: how often do pairs vote for the same target."""
        votes_by_round: dict[int, dict[str, str]] = {}
        for u, v, data in self._graph.edges(data=True):
            if data.get("type") != EdgeType.VOTES_FOR:
                continue
            r = data.get("round", 0)
            votes_by_round.setdefault(r, {})[u] = v

        alignment: dict[tuple[str, str], int] = {}
        for _round, votes in votes_by_round.items():
            voters = list(votes.keys())
            for i, v1 in enumerate(voters):
                for v2 in voters[i + 1:]:
                    pair = (min(v1, v2), max(v1, v2))
                    if votes[v1] == votes[v2]:
                        alignment[pair] = alignment.get(pair, 0) + 1
        self._vote_alignment = alignment

    def _compute_faction_clusters(self) -> None:
        """Simple faction clustering based on vote alignment + defense edges."""
        players = self.get_player_nodes()
        if len(players) < 3:
            self._faction_clusters = {}
            return

        affinity = nx.Graph()
        affinity.add_nodes_from(players)

        for (p1, p2), count in self._vote_alignment.items():
            if affinity.has_node(p1) and affinity.has_node(p2):
                affinity.add_edge(p1, p2, weight=count)

        for u, v, data in self._graph.edges(data=True):
            if data.get("type") == EdgeType.DEFENDS:
                if affinity.has_node(u) and affinity.has_node(v):
                    w = affinity[u][v]["weight"] if affinity.has_edge(u, v) else 0
                    affinity.add_edge(u, v, weight=w + 1)

        try:
            communities = nx.community.greedy_modularity_communities(affinity)
            self._faction_clusters = {
                "faction_%d" % (i + 1): sorted(list(c))
                for i, c in enumerate(communities)
            }
            logger.debug("Faction clustering: %d communities found", len(self._faction_clusters))
        except Exception:
            logger.debug("Faction clustering failed (insufficient edges), skipping")
            self._faction_clusters = {}

    def _generate_public_summary(self) -> None:
        """Generate public summary text from cached analysis."""
        parts: list[str] = []
        parts.append(self._format_faction_summary())
        parts.append(self._format_conflict_summary())
        parts.append(self._format_vote_alignment_summary())
        self._public_summary_text = "\n".join(p for p in parts if p)

    def _format_faction_summary(self) -> str:
        if not self._faction_clusters:
            return ""
        lines = ["阵营聚类假设："]
        for name, members in self._faction_clusters.items():
            lines.append("  %s: {%s}" % (name, ", ".join(members)))
        return "\n".join(lines)

    def _format_conflict_summary(self) -> str:
        if not self._public_conflicts:
            return ""
        lines = ["已检测到的公开矛盾 (%d 条)：" % len(self._public_conflicts)]
        for i, c in enumerate(self._public_conflicts, 1):
            lines.append("  %d. [%s] %s" % (i, c.severity.value, c.description))
        return "\n".join(lines)

    def _format_vote_alignment_summary(self) -> str:
        if not self._vote_alignment:
            return ""
        high_alignment = [
            (pair, count) for pair, count in self._vote_alignment.items()
            if count >= 2
        ]
        if not high_alignment:
            return ""
        lines = ["投票高度一致的玩家对："]
        for (p1, p2), count in sorted(high_alignment, key=lambda x: -x[1]):
            lines.append("  %s 和 %s：%d 轮投票一致" % (p1, p2, count))
        return "\n".join(lines)

    # ══════════════════════════════════════════════
    #  Utility helpers
    # ══════════════════════════════════════════════

    def _get_edges_in_round(self, edge_type: EdgeType, round_number: int) -> list[dict]:
        results = []
        for u, v, data in self._graph.edges(data=True):
            if data.get("type") == edge_type and data.get("round") == round_number:
                results.append({"source": u, "target": v, **data})
        return results

    def _get_rounds_for_edge(self, source: str, target: str, edge_type: EdgeType) -> list[int]:
        rounds = []
        if self._graph.has_node(source) and self._graph.has_node(target):
            for _key, data in self._graph[source][target].items():
                if data.get("type") == edge_type:
                    rounds.append(data.get("round", 0))
        return rounds
