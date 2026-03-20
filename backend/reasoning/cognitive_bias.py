"""CognitiveBias — maps player persona to quantified reasoning preferences.

Same public graph facts pass through different cognitive filters,
producing different conclusions for different players. This is what
prevents all villagers from reaching identical decisions.
"""

import re

from backend.reasoning.models import (
    AttentionFocus,
    CognitiveBias,
    Conflict,
)


# ══════════════════════════════════════════════
#  Predefined bias templates
# ══════════════════════════════════════════════

BIAS_TEMPLATES: dict[str, CognitiveBias] = {
    "impulsive": CognitiveBias(
        evidence_weights={
            "speech_contradiction": 1.5,
            "vote_pattern": 0.7,
            "role_claim_conflict": 1.2,
            "social_consensus": 1.0,
            "attitude_flip": 1.4,
        },
        conclusion_threshold=0.3,
        attention_focus=AttentionFocus.RECENT,
        stubbornness=0.3,
    ),
    "analytical": CognitiveBias(
        evidence_weights={
            "speech_contradiction": 1.0,
            "vote_pattern": 1.5,
            "role_claim_conflict": 1.3,
            "social_consensus": 0.5,
            "attitude_flip": 1.2,
        },
        conclusion_threshold=0.7,
        attention_focus=AttentionFocus.LONG_TERM,
        stubbornness=0.8,
    ),
    "conformist": CognitiveBias(
        evidence_weights={
            "speech_contradiction": 0.6,
            "vote_pattern": 0.8,
            "role_claim_conflict": 0.9,
            "social_consensus": 1.8,
            "attitude_flip": 0.7,
        },
        conclusion_threshold=0.4,
        attention_focus=AttentionFocus.SOCIAL,
        stubbornness=0.2,
    ),
    "hesitant": CognitiveBias(
        evidence_weights={
            "speech_contradiction": 1.0,
            "vote_pattern": 1.0,
            "role_claim_conflict": 1.0,
            "social_consensus": 0.8,
            "attitude_flip": 0.9,
        },
        conclusion_threshold=0.9,
        attention_focus=AttentionFocus.DETAIL,
        stubbornness=0.2,
    ),
    "aggressive": CognitiveBias(
        evidence_weights={
            "speech_contradiction": 1.3,
            "vote_pattern": 1.0,
            "role_claim_conflict": 1.5,
            "social_consensus": 0.6,
            "attitude_flip": 1.3,
        },
        conclusion_threshold=0.25,
        attention_focus=AttentionFocus.RECENT,
        stubbornness=0.7,
    ),
    "observant": CognitiveBias(
        evidence_weights={
            "speech_contradiction": 1.2,
            "vote_pattern": 1.3,
            "role_claim_conflict": 1.1,
            "social_consensus": 0.7,
            "attitude_flip": 1.5,
        },
        conclusion_threshold=0.6,
        attention_focus=AttentionFocus.DETAIL,
        stubbornness=0.6,
    ),
}

# Keyword → template name mapping (Chinese + English)
_PERSONA_KEYWORDS: dict[str, str] = {
    "冲动": "impulsive",
    "果断": "impulsive",
    "急躁": "impulsive",
    "impulsive": "impulsive",
    "深沉": "analytical",
    "分析": "analytical",
    "逻辑": "analytical",
    "理性": "analytical",
    "analytical": "analytical",
    "从众": "conformist",
    "随和": "conformist",
    "合群": "conformist",
    "conformist": "conformist",
    "犹豫": "hesitant",
    "纠结": "hesitant",
    "谨慎": "hesitant",
    "hesitant": "hesitant",
    "激进": "aggressive",
    "强势": "aggressive",
    "aggressive": "aggressive",
    "观察": "observant",
    "细心": "observant",
    "敏锐": "observant",
    "observant": "observant",
}

_NEUTRAL_BIAS = CognitiveBias()


# ══════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════

def resolve_cognitive_bias(persona: str) -> CognitiveBias:
    """Map a persona description to the closest cognitive bias template.

    Scans persona text for keywords. First match wins.
    Returns neutral bias (all weights 1.0, threshold 0.5) if no match.
    """
    if not persona:
        return CognitiveBias()

    matched_template = _match_persona_to_template(persona)
    if matched_template:
        return matched_template
    return CognitiveBias()


def apply_bias_to_conflicts(
    conflicts: list[Conflict],
    bias: CognitiveBias,
) -> list[Conflict]:
    """Re-weight and sort conflicts according to cognitive bias.

    Impulsive types see speech contradictions first with amplified severity.
    Analytical types see vote patterns first.
    Conformist types see socially-prominent conflicts first.
    """
    scored = _score_conflicts(conflicts, bias)
    scored.sort(key=lambda pair: -pair[1])
    return [c for c, _score in scored]


def apply_bias_to_trust(
    base_trust: dict[str, float],
    bias: CognitiveBias,
    vote_alignment: dict[tuple[str, str], int],
    player_id: str,
) -> dict[str, float]:
    """Adjust trust scores based on cognitive bias.

    Conformist: players trusted by many → trust boost.
    Analytical: players with consistent voting patterns → trust boost.
    Impulsive: recent suspicious behavior → trust drops fast.
    """
    adjusted = dict(base_trust)
    adjusted = _apply_social_consensus_factor(adjusted, bias, vote_alignment, player_id)
    adjusted = _apply_attention_focus_factor(adjusted, bias)
    return adjusted


# ══════════════════════════════════════════════
#  Private step methods
# ══════════════════════════════════════════════

def _match_persona_to_template(persona: str) -> CognitiveBias | None:
    """Scan persona text for keywords and return matching template."""
    persona_lower = persona.lower()
    for keyword, template_name in _PERSONA_KEYWORDS.items():
        if keyword in persona_lower:
            return BIAS_TEMPLATES[template_name]
    return None


def _score_conflicts(
    conflicts: list[Conflict],
    bias: CognitiveBias,
) -> list[tuple[Conflict, float]]:
    """Score each conflict by multiplying its evidence type weight."""
    scored = []
    for conflict in conflicts:
        evidence_type = conflict.evidence_type or "speech_contradiction"
        weight = bias.evidence_weights.get(evidence_type, 1.0)
        severity_score = {"low": 1.0, "medium": 2.0, "high": 3.0}.get(
            conflict.severity.value, 1.0,
        )
        scored.append((conflict, weight * severity_score))
    return scored


def _apply_social_consensus_factor(
    trust: dict[str, float],
    bias: CognitiveBias,
    vote_alignment: dict[tuple[str, str], int],
    player_id: str,
) -> dict[str, float]:
    """Boost trust for players who vote similarly to many others (conformist effect)."""
    social_weight = bias.evidence_weights.get("social_consensus", 1.0)
    if social_weight <= 1.0:
        return trust

    # Count how many alignment pairs each player appears in
    alignment_count: dict[str, int] = {}
    for (p1, p2), count in vote_alignment.items():
        alignment_count[p1] = alignment_count.get(p1, 0) + count
        alignment_count[p2] = alignment_count.get(p2, 0) + count

    if not alignment_count:
        return trust

    max_count = max(alignment_count.values())
    if max_count == 0:
        return trust

    for pid in trust:
        if pid == player_id:
            continue
        normalized = alignment_count.get(pid, 0) / max_count
        boost = normalized * (social_weight - 1.0) * 0.3
        trust[pid] = trust[pid] + boost

    return trust


def _apply_attention_focus_factor(
    trust: dict[str, float],
    bias: CognitiveBias,
) -> dict[str, float]:
    """Apply minor adjustments based on attention focus type.

    This is a lightweight modifier — the main differentiation comes
    from conflict scoring and conclusion thresholds, not trust values.
    """
    # Attention focus primarily affects which conflicts/chains are highlighted
    # in the summarizer, not trust scores directly. Kept as a no-op placeholder
    # for future refinement.
    return trust
