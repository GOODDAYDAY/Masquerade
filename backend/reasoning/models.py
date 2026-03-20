"""Data models for the Game Reasoning Graph.

Defines graph nodes, edges, conflicts, cognitive biases, reasoning chains,
and the final summary structure injected into LLM prompts.
"""

from dataclasses import dataclass, field
from enum import Enum


# ──────────────────────────────────────────────
#  Graph nodes and edges
# ──────────────────────────────────────────────

class NodeType(Enum):
    PLAYER = "player"
    CLAIM = "claim"
    EVENT = "event"


class EdgeType(Enum):
    VOTES_FOR = "votes_for"
    ACCUSES = "accuses"
    DEFENDS = "defends"
    CLAIMS_ROLE = "claims_role"
    CONTRADICTS = "contradicts"
    VERIFIED = "verified"
    TEAMMATE = "teammate"
    KILLED = "killed"


@dataclass
class GraphNode:
    id: str
    type: NodeType
    round: int = 0
    attrs: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    type: EdgeType
    round: int = 0
    weight: float = 1.0
    attrs: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
#  Conflicts
# ──────────────────────────────────────────────

class ConflictSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Conflict:
    description: str
    severity: ConflictSeverity
    involved_players: list[str]
    round_detected: int
    evidence_type: str = ""
    evidence: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
#  Cognitive biases
# ──────────────────────────────────────────────

class AttentionFocus(Enum):
    RECENT = "recent"
    LONG_TERM = "long_term"
    SOCIAL = "social"
    DETAIL = "detail"


@dataclass
class CognitiveBias:
    """Quantified reasoning preferences derived from player persona."""

    evidence_weights: dict[str, float] = field(default_factory=lambda: {
        "speech_contradiction": 1.0,
        "vote_pattern": 1.0,
        "role_claim_conflict": 1.0,
        "social_consensus": 1.0,
        "attitude_flip": 1.0,
    })
    conclusion_threshold: float = 0.5
    attention_focus: AttentionFocus = AttentionFocus.DETAIL
    stubbornness: float = 0.5


# ──────────────────────────────────────────────
#  Reasoning chains
# ──────────────────────────────────────────────

@dataclass
class ReasoningChain:
    """A logical inference path: premises → conclusion."""

    premises: list[str]
    conclusion: str
    confidence: float
    path: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
#  Graph summary (injected into LLM prompts)
# ──────────────────────────────────────────────

@dataclass
class GraphSummary:
    """Structured summary ready for Thinker/Evaluator prompt injection."""

    faction_hypothesis: str = ""
    active_conflicts: list[str] = field(default_factory=list)
    reasoning_chains: list[str] = field(default_factory=list)
    trust_map: dict[str, float] = field(default_factory=dict)
    suspicion_map: dict[str, float] = field(default_factory=dict)
    attention_hint: str = ""
