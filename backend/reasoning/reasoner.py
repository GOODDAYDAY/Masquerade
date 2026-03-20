"""Reasoner — graph-based logical inference engine.

Computes trust/suspicion scores and builds reasoning chains by combining
shared graph structure, private knowledge, and cognitive bias.
All computation is programmatic — zero LLM calls.
"""

from backend.core.logging import get_logger
from backend.reasoning.cognitive_bias import apply_bias_to_trust
from backend.reasoning.models import (
    CognitiveBias,
    EdgeType,
    ReasoningChain,
)
from backend.reasoning.private_overlay import PrivateOverlay
from backend.reasoning.shared_graph import SharedGraph

logger = get_logger("reasoning.reasoner")


class Reasoner:
    """Computes trust/suspicion maps and reasoning chains for a player."""

    # ══════════════════════════════════════════════
    #  Public orchestration methods
    # ══════════════════════════════════════════════

    def reason(
        self,
        player_id: str,
        shared: SharedGraph,
        overlay: PrivateOverlay,
        bias: CognitiveBias,
        alive_players: list[str],
    ) -> tuple[dict[str, float], dict[str, float], list[ReasoningChain]]:
        """Execute full reasoning pipeline, return (trust, suspicion, chains)."""
        # 1. Compute base trust/suspicion from public graph (defense, accusation, conflicts)
        base_trust, base_suspicion = self._compute_base_scores(shared, alive_players, player_id)
        # 2. Override with private knowledge (seer results, teammate info)
        trust, suspicion = self._apply_private_knowledge(overlay, base_trust, base_suspicion)
        # 3. Apply cognitive bias to adjust trust (conformist boost, etc.)
        trust = apply_bias_to_trust(trust, bias, shared.get_vote_alignment(), player_id)
        # 4. Build reasoning chains from graph paths and private inferences
        chains = self._build_reasoning_chains(shared, overlay, bias, player_id)
        logger.debug("[%s] Reasoning complete: %d trust scores, %d chains",
                      player_id, len(trust), len(chains))
        return trust, suspicion, chains

    # ══════════════════════════════════════════════
    #  Private step methods
    # ══════════════════════════════════════════════

    def _compute_base_scores(
        self,
        shared: SharedGraph,
        alive_players: list[str],
        player_id: str,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute base trust/suspicion from public graph edges."""
        # Initialize: all alive players start at neutral trust, zero suspicion
        trust: dict[str, float] = {p: 0.5 for p in alive_players if p != player_id}
        suspicion: dict[str, float] = {p: 0.0 for p in alive_players if p != player_id}

        # Adjust based on public graph signals
        self._apply_defense_signals(shared, trust, player_id)
        self._apply_accusation_signals(shared, suspicion, player_id)
        self._apply_conflict_signals(shared, suspicion)
        self._clamp_scores(trust)
        self._clamp_scores(suspicion)

        return trust, suspicion

    def _apply_defense_signals(
        self, shared: SharedGraph, trust: dict[str, float], player_id: str,
    ) -> None:
        """Boost trust for players who defended me or were defended by many."""
        defense_edges = shared.get_edges_by_type(EdgeType.DEFENDS)
        for edge in defense_edges:
            defender = edge["source"]
            defended = edge["target"]
            if defended == player_id and defender in trust:
                trust[defender] = trust.get(defender, 0.5) + 0.15
            if defender == player_id and defended in trust:
                trust[defended] = trust.get(defended, 0.5) + 0.1

    def _apply_accusation_signals(
        self, shared: SharedGraph, suspicion: dict[str, float], player_id: str,
    ) -> None:
        """Raise suspicion for players accused by multiple others."""
        accuse_edges = shared.get_edges_by_type(EdgeType.ACCUSES)
        accuse_count: dict[str, int] = {}
        for edge in accuse_edges:
            accused = edge["target"]
            accuse_count[accused] = accuse_count.get(accused, 0) + 1

        for pid, count in accuse_count.items():
            if pid in suspicion and pid != player_id:
                suspicion[pid] = suspicion.get(pid, 0.0) + count * 0.1

    def _apply_conflict_signals(
        self, shared: SharedGraph, suspicion: dict[str, float],
    ) -> None:
        """Raise suspicion for players involved in public conflicts."""
        conflicts = shared.get_public_conflicts()
        for conflict in conflicts:
            bump = {"low": 0.05, "medium": 0.1, "high": 0.2}.get(
                conflict.severity.value, 0.05,
            )
            for pid in conflict.involved_players:
                if pid in suspicion:
                    suspicion[pid] = suspicion.get(pid, 0.0) + bump

    def _apply_private_knowledge(
        self,
        overlay: PrivateOverlay,
        trust: dict[str, float],
        suspicion: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Override scores using private knowledge (seer results, teammates)."""
        for wolf in overlay.get_known_wolves():
            if wolf in suspicion:
                suspicion[wolf] = 1.0
                trust[wolf] = 0.0

        for good in overlay.get_known_good():
            if good in trust:
                trust[good] = 1.0
                suspicion[good] = 0.0

        for teammate in overlay.get_teammates():
            if teammate in trust:
                trust[teammate] = 1.0
                suspicion[teammate] = 0.0

        # Apply inference-based adjustments
        for inference in overlay.get_inferences():
            self._apply_inference_adjustment(inference, trust, suspicion)

        self._clamp_scores(trust)
        self._clamp_scores(suspicion)
        return trust, suspicion

    def _apply_inference_adjustment(
        self,
        inference: ReasoningChain,
        trust: dict[str, float],
        suspicion: dict[str, float],
    ) -> None:
        """Adjust scores based on a single inference chain."""
        if not inference.path:
            return
        subject = inference.path[0]
        if subject not in suspicion:
            return

        suspicion[subject] = suspicion.get(subject, 0.0) + inference.confidence * 0.3
        trust[subject] = max(0.0, trust.get(subject, 0.5) - inference.confidence * 0.2)

    def _build_reasoning_chains(
        self,
        shared: SharedGraph,
        overlay: PrivateOverlay,
        bias: CognitiveBias,
        player_id: str,
    ) -> list[ReasoningChain]:
        """Build reasoning chains from graph paths and private inferences."""
        chains: list[ReasoningChain] = []
        # Chains from private knowledge (seer verified wolf → defender is suspect)
        chains.extend(self._chains_from_private_inferences(overlay))
        # Chains from role claim conflicts (two prophets → one is fake)
        chains.extend(self._chains_from_role_conflicts(shared))
        # Chains from suspicious vote alignment (same target 2+ rounds)
        chains.extend(self._chains_from_vote_patterns(shared, player_id))
        # Filter by cognitive bias threshold and sort by confidence
        chains = self._filter_chains_by_bias(chains, bias)
        return chains

    def _chains_from_private_inferences(self, overlay: PrivateOverlay) -> list[ReasoningChain]:
        """Convert private inferences directly to reasoning chains."""
        return list(overlay.get_inferences())

    def _chains_from_role_conflicts(self, shared: SharedGraph) -> list[ReasoningChain]:
        """Build chains from role claim conflicts (e.g., two prophets → one is fake)."""
        chains: list[ReasoningChain] = []
        conflicts = shared.get_public_conflicts()
        for conflict in conflicts:
            if conflict.evidence_type == "role_claim_conflict":
                chains.append(ReasoningChain(
                    premises=conflict.evidence,
                    conclusion=conflict.description,
                    confidence=0.9,
                    path=conflict.involved_players,
                ))
        return chains

    def _chains_from_vote_patterns(
        self, shared: SharedGraph, player_id: str,
    ) -> list[ReasoningChain]:
        """Build chains from suspicious vote alignment patterns."""
        chains: list[ReasoningChain] = []
        alignment = shared.get_vote_alignment()
        for (p1, p2), count in alignment.items():
            if count >= 2 and p1 != player_id and p2 != player_id:
                chains.append(ReasoningChain(
                    premises=[
                        "%s 和 %s 连续 %d 轮投票目标一致" % (p1, p2, count),
                    ],
                    conclusion="%s 和 %s 可能是同阵营" % (p1, p2),
                    confidence=min(0.4 + count * 0.15, 0.85),
                    path=[p1, p2],
                ))
        return chains

    def _filter_chains_by_bias(
        self, chains: list[ReasoningChain], bias: CognitiveBias,
    ) -> list[ReasoningChain]:
        """Filter chains by conclusion threshold and sort by confidence."""
        filtered = [c for c in chains if c.confidence >= bias.conclusion_threshold]
        filtered.sort(key=lambda c: -c.confidence)
        return filtered[:10]

    def _clamp_scores(self, scores: dict[str, float]) -> None:
        """Clamp all scores to [0.0, 1.0]."""
        for key in scores:
            scores[key] = max(0.0, min(1.0, scores[key]))
