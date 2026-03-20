"""GraphSummarizer — converts graph state to structured text for LLM injection.

Produces two outputs:
- Thinker context: faction hypothesis, reasoning chains, trust/suspicion map, attention hint
- Evaluator context: active conflict list for validation
"""

from backend.reasoning.models import (
    AttentionFocus,
    CognitiveBias,
    Conflict,
    GraphSummary,
    ReasoningChain,
)
from backend.reasoning.shared_graph import SharedGraph


class GraphSummarizer:
    """Converts graph analysis results to prompt-injectable text."""

    # ══════════════════════════════════════════════
    #  Public orchestration methods
    # ══════════════════════════════════════════════

    def summarize(
        self,
        shared: SharedGraph,
        trust_map: dict[str, float],
        suspicion_map: dict[str, float],
        conflicts: list[Conflict],
        chains: list[ReasoningChain],
        bias: CognitiveBias,
    ) -> GraphSummary:
        """Build a complete graph summary."""
        faction_text = self._format_faction_hypothesis(shared)
        conflict_texts = self._format_conflicts(conflicts)
        chain_texts = self._format_reasoning_chains(chains)
        attention = self._generate_attention_hint(bias, conflicts)
        return GraphSummary(
            faction_hypothesis=faction_text,
            active_conflicts=conflict_texts,
            reasoning_chains=chain_texts,
            trust_map=trust_map,
            suspicion_map=suspicion_map,
            attention_hint=attention,
        )

    def to_thinker_text(self, summary: GraphSummary) -> str:
        """Format GraphSummary as a text block for Thinker prompt injection."""
        sections: list[str] = []
        sections.append(self._render_faction_section(summary))
        sections.append(self._render_conflict_section(summary))
        sections.append(self._render_chain_section(summary))
        sections.append(self._render_trust_section(summary))
        sections.append(self._render_attention_section(summary))
        return "\n".join(s for s in sections if s)

    def to_evaluator_text(self, conflicts: list[Conflict]) -> str:
        """Format conflict list as a text block for Evaluator prompt injection."""
        if not conflicts:
            return ""
        lines = ["以下是图谱分析检测到的矛盾，请确认你的策略是否充分考虑了这些信息："]
        for i, c in enumerate(conflicts, 1):
            lines.append("  %d. [%s] %s" % (i, c.severity.value, c.description))
            if c.evidence:
                for ev in c.evidence:
                    lines.append("     证据: %s" % ev)
        return "\n".join(lines)

    # ══════════════════════════════════════════════
    #  Private step methods — summarize
    # ══════════════════════════════════════════════

    def _format_faction_hypothesis(self, shared: SharedGraph) -> str:
        """Format faction clustering as text."""
        clusters = shared.get_faction_clusters()
        if not clusters:
            return ""
        parts = []
        for name, members in clusters.items():
            parts.append("{%s}" % ", ".join(members))
        return " vs ".join(parts)

    def _format_conflicts(self, conflicts: list[Conflict]) -> list[str]:
        """Format conflict list to text lines."""
        return [
            "[%s] %s" % (c.severity.value, c.description)
            for c in conflicts[:8]
        ]

    def _format_reasoning_chains(self, chains: list[ReasoningChain]) -> list[str]:
        """Format reasoning chains to text lines."""
        texts: list[str] = []
        for chain in chains[:6]:
            premise_text = " + ".join(chain.premises)
            texts.append(
                "%s → %s (置信度: %.0f%%)" % (
                    premise_text, chain.conclusion, chain.confidence * 100,
                )
            )
        return texts

    def _generate_attention_hint(
        self, bias: CognitiveBias, conflicts: list[Conflict],
    ) -> str:
        """Generate a persona-appropriate attention hint."""
        hints = {
            AttentionFocus.RECENT: "重点关注最近一轮的新信息和变化",
            AttentionFocus.LONG_TERM: "重点关注跨轮次的投票趋势和态度变化",
            AttentionFocus.SOCIAL: "重点关注多数玩家的共识方向",
            AttentionFocus.DETAIL: "重点关注细节证据和逻辑链的完整性",
        }
        base_hint = hints.get(bias.attention_focus, "")

        if bias.conclusion_threshold >= 0.7:
            base_hint += "；谨慎下结论，需要充分证据"
        elif bias.conclusion_threshold <= 0.35:
            base_hint += "；可以基于初步判断快速行动"

        return base_hint

    # ══════════════════════════════════════════════
    #  Private step methods — to_thinker_text
    # ══════════════════════════════════════════════

    def _render_faction_section(self, summary: GraphSummary) -> str:
        if not summary.faction_hypothesis:
            return ""
        return "阵营假设：%s" % summary.faction_hypothesis

    def _render_conflict_section(self, summary: GraphSummary) -> str:
        if not summary.active_conflicts:
            return ""
        lines = ["已检测到的矛盾："]
        for i, text in enumerate(summary.active_conflicts, 1):
            lines.append("  %d. %s" % (i, text))
        return "\n".join(lines)

    def _render_chain_section(self, summary: GraphSummary) -> str:
        if not summary.reasoning_chains:
            return ""
        lines = ["推理链："]
        for i, text in enumerate(summary.reasoning_chains, 1):
            lines.append("  %d. %s" % (i, text))
        return "\n".join(lines)

    def _render_trust_section(self, summary: GraphSummary) -> str:
        """Render trust/suspicion as a compact heatmap."""
        if not summary.trust_map and not summary.suspicion_map:
            return ""

        lines = ["信任/怀疑评估："]
        all_players = sorted(
            set(list(summary.trust_map.keys()) + list(summary.suspicion_map.keys()))
        )
        for pid in all_players:
            trust = summary.trust_map.get(pid, 0.5)
            suspicion = summary.suspicion_map.get(pid, 0.0)
            label = self._trust_label(trust, suspicion)
            lines.append("  %s: %s (信任%.0f%% 怀疑%.0f%%)" % (
                pid, label, trust * 100, suspicion * 100,
            ))
        return "\n".join(lines)

    def _render_attention_section(self, summary: GraphSummary) -> str:
        if not summary.attention_hint:
            return ""
        return "关注建议：%s" % summary.attention_hint

    def _trust_label(self, trust: float, suspicion: float) -> str:
        """Convert trust/suspicion scores to a human-readable label."""
        if trust >= 0.8:
            return "高度可信"
        if suspicion >= 0.8:
            return "高度可疑"
        if trust >= 0.6:
            return "较可信"
        if suspicion >= 0.5:
            return "较可疑"
        if suspicion >= 0.3:
            return "有些可疑"
        return "待观察"
