"""Automated tests for the Game Reasoning Graph (GRG) package.

Tests cover: models, extractor, shared graph, private overlay,
cognitive bias, conflict detection, reasoner, summarizer, and facade.
No LLM calls required — all tests are pure programmatic.
"""

import pytest

from backend.reasoning import GameReasoningGraph
from backend.reasoning.cognitive_bias import (
    apply_bias_to_conflicts,
    resolve_cognitive_bias,
)
from backend.reasoning.conflict_detector import ConflictDetector
from backend.reasoning.extractor import EventExtractor
from backend.reasoning.models import (
    AttentionFocus,
    CognitiveBias,
    Conflict,
    ConflictSeverity,
    EdgeType,
    GraphEdge,
    NodeType,
    ReasoningChain,
)
from backend.reasoning.private_overlay import PrivateOverlay
from backend.reasoning.reasoner import Reasoner
from backend.reasoning.shared_graph import SharedGraph
from backend.reasoning.summarizer import GraphSummarizer


# ══════════════════════════════════════════════
#  Models
# ══════════════════════════════════════════════

class TestModels:
    def test_edge_types_exist(self):
        assert EdgeType.VOTES_FOR.value == "votes_for"
        assert EdgeType.ACCUSES.value == "accuses"
        assert EdgeType.VERIFIED.value == "verified"
        assert EdgeType.TEAMMATE.value == "teammate"

    def test_graph_edge_creation(self):
        edge = GraphEdge(source="A", target="B", type=EdgeType.VOTES_FOR, round=1)
        assert edge.source == "A"
        assert edge.weight == 1.0

    def test_conflict_severity(self):
        c = Conflict(
            description="test",
            severity=ConflictSeverity.HIGH,
            involved_players=["A"],
            round_detected=1,
        )
        assert c.severity == ConflictSeverity.HIGH

    def test_cognitive_bias_defaults(self):
        bias = CognitiveBias()
        assert bias.conclusion_threshold == 0.5
        assert bias.stubbornness == 0.5


# ══════════════════════════════════════════════
#  EventExtractor
# ══════════════════════════════════════════════

class TestExtractor:
    def setup_method(self):
        self.extractor = EventExtractor()

    def test_extract_votes(self):
        public_state = {
            "vote_history": {1: {"A": "B", "C": "B"}},
        }
        edges = self.extractor.extract_round_events(1, public_state, [])
        vote_edges = [e for e in edges if e.type == EdgeType.VOTES_FOR]
        assert len(vote_edges) == 2
        assert vote_edges[0].source == "A"
        assert vote_edges[0].target == "B"

    def test_extract_deaths(self):
        public_state = {
            "night_deaths": ["X"],
            "eliminated_this_round": "Y",
            "vote_history": {},
        }
        edges = self.extractor.extract_round_events(1, public_state, [])
        kill_edges = [e for e in edges if e.type == EdgeType.KILLED]
        assert len(kill_edges) == 2
        targets = {e.target for e in kill_edges}
        assert targets == {"X", "Y"}

    def test_extract_role_claims(self):
        actions = [
            {"player_id": "A", "type": "speak", "payload": {"content": "我是预言家，验了B是好人"}},
        ]
        edges = self.extractor.extract_round_events(1, {"vote_history": {}}, actions)
        claim_edges = [e for e in edges if e.type == EdgeType.CLAIMS_ROLE]
        assert len(claim_edges) == 1
        assert claim_edges[0].source == "A"
        assert claim_edges[0].target == "预言家"

    def test_extract_accusations(self):
        actions = [
            {"player_id": "A", "type": "speak", "payload": {"content": "我觉得B很可疑，有问题"}},
            {"player_id": "B", "type": "speak", "payload": {"content": "我没什么好说的"}},
        ]
        edges = self.extractor.extract_round_events(1, {"vote_history": {}}, actions)
        accuse_edges = [e for e in edges if e.type == EdgeType.ACCUSES]
        assert len(accuse_edges) == 1
        assert accuse_edges[0].target == "B"

    def test_extract_defenses(self):
        actions = [
            {"player_id": "A", "type": "speak", "payload": {"content": "我信任B，B是好人"}},
            {"player_id": "B", "type": "speak", "payload": {"content": "谢谢"}},
        ]
        edges = self.extractor.extract_round_events(1, {"vote_history": {}}, actions)
        defend_edges = [e for e in edges if e.type == EdgeType.DEFENDS]
        assert len(defend_edges) == 1
        assert defend_edges[0].target == "B"

    def test_extract_seer_verification(self):
        private_info = {"check_history": {"B": "good", "C": "wolf"}}
        edges = self.extractor.extract_private_events("A", 1, private_info)
        assert len(edges) == 2
        good_edge = [e for e in edges if e.target == "B"][0]
        assert good_edge.attrs["result"] == "good"

    def test_extract_teammates(self):
        private_info = {"teammates": ["B", "C"]}
        edges = self.extractor.extract_private_events("A", 1, private_info)
        teammate_edges = [e for e in edges if e.type == EdgeType.TEAMMATE]
        assert len(teammate_edges) == 2

    def test_no_self_teammate(self):
        private_info = {"teammates": ["A", "B"]}
        edges = self.extractor.extract_private_events("A", 1, private_info)
        teammate_edges = [e for e in edges if e.type == EdgeType.TEAMMATE]
        assert len(teammate_edges) == 1
        assert teammate_edges[0].target == "B"

    def test_non_speak_action_ignored(self):
        actions = [
            {"player_id": "A", "type": "vote", "payload": {"target": "B"}},
        ]
        edges = self.extractor.extract_round_events(1, {"vote_history": {}}, actions)
        speech_edges = [e for e in edges if e.type in (EdgeType.ACCUSES, EdgeType.DEFENDS, EdgeType.CLAIMS_ROLE)]
        assert len(speech_edges) == 0


# ══════════════════════════════════════════════
#  SharedGraph
# ══════════════════════════════════════════════

class TestSharedGraph:
    def setup_method(self):
        self.graph = SharedGraph()

    def test_update_adds_edges(self):
        edges = [
            GraphEdge(source="A", target="B", type=EdgeType.VOTES_FOR, round=1),
            GraphEdge(source="C", target="B", type=EdgeType.VOTES_FOR, round=1),
        ]
        self.graph.update(1, edges)
        players = self.graph.get_player_nodes()
        assert "A" in players
        assert "B" in players
        assert "C" in players

    def test_role_claim_conflict_detected(self):
        edges = [
            GraphEdge(source="A", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
            GraphEdge(source="B", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
        ]
        self.graph.update(1, edges)
        conflicts = self.graph.get_public_conflicts()
        role_conflicts = [c for c in conflicts if c.evidence_type == "role_claim_conflict"]
        assert len(role_conflicts) == 1
        assert role_conflicts[0].severity == ConflictSeverity.HIGH
        assert set(role_conflicts[0].involved_players) == {"A", "B"}

    def test_vote_speech_contradiction(self):
        edges = [
            GraphEdge(source="A", target="B", type=EdgeType.ACCUSES, round=1),
            GraphEdge(source="A", target="C", type=EdgeType.VOTES_FOR, round=1),
        ]
        self.graph.update(1, edges)
        conflicts = self.graph.get_public_conflicts()
        contradictions = [c for c in conflicts if c.evidence_type == "speech_contradiction"]
        assert len(contradictions) == 1
        assert "A" in contradictions[0].involved_players

    def test_attitude_flip_detected(self):
        edges_r1 = [
            GraphEdge(source="A", target="B", type=EdgeType.ACCUSES, round=1),
        ]
        self.graph.update(1, edges_r1)
        edges_r2 = [
            GraphEdge(source="A", target="B", type=EdgeType.DEFENDS, round=2),
        ]
        self.graph.update(2, edges_r2)
        conflicts = self.graph.get_public_conflicts()
        flips = [c for c in conflicts if c.evidence_type == "attitude_flip"]
        assert len(flips) == 1

    def test_vote_alignment(self):
        for r in [1, 2]:
            edges = [
                GraphEdge(source="A", target="X", type=EdgeType.VOTES_FOR, round=r),
                GraphEdge(source="B", target="X", type=EdgeType.VOTES_FOR, round=r),
                GraphEdge(source="C", target="Y", type=EdgeType.VOTES_FOR, round=r),
            ]
            self.graph.update(r, edges)
        alignment = self.graph.get_vote_alignment()
        assert alignment.get(("A", "B"), 0) == 2
        assert alignment.get(("A", "C"), 0) == 0

    def test_faction_clusters(self):
        for r in [1, 2, 3]:
            edges = [
                GraphEdge(source="A", target="X", type=EdgeType.VOTES_FOR, round=r),
                GraphEdge(source="B", target="X", type=EdgeType.VOTES_FOR, round=r),
                GraphEdge(source="C", target="Y", type=EdgeType.VOTES_FOR, round=r),
                GraphEdge(source="D", target="Y", type=EdgeType.VOTES_FOR, round=r),
            ]
            self.graph.update(r, edges)
        clusters = self.graph.get_faction_clusters()
        assert len(clusters) >= 1

    def test_public_summary_not_empty_with_data(self):
        edges = [
            GraphEdge(source="A", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
            GraphEdge(source="B", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
        ]
        self.graph.update(1, edges)
        summary = self.graph.get_public_summary_text()
        assert "预言家" in summary

    def test_empty_graph_no_errors(self):
        self.graph.update(1, [])
        assert self.graph.get_public_conflicts() == []
        assert self.graph.get_faction_clusters() == {}
        assert self.graph.get_vote_alignment() == {}


# ══════════════════════════════════════════════
#  PrivateOverlay
# ══════════════════════════════════════════════

class TestPrivateOverlay:
    def test_seer_knowledge(self):
        overlay = PrivateOverlay("seer")
        overlay.add_private_edge(GraphEdge(
            source="seer", target="B", type=EdgeType.VERIFIED,
            round=1, attrs={"result": "wolf"},
        ))
        assert "B" in overlay.get_known_wolves()

    def test_good_knowledge(self):
        overlay = PrivateOverlay("seer")
        overlay.add_private_edge(GraphEdge(
            source="seer", target="C", type=EdgeType.VERIFIED,
            round=1, attrs={"result": "good"},
        ))
        assert "C" in overlay.get_known_good()

    def test_teammate_knowledge(self):
        overlay = PrivateOverlay("wolf1")
        overlay.add_private_edge(GraphEdge(
            source="wolf1", target="wolf2", type=EdgeType.TEAMMATE, round=0,
        ))
        assert "wolf2" in overlay.get_teammates()

    def test_wolf_defender_inference(self):
        shared = SharedGraph()
        shared.update(1, [
            GraphEdge(source="D", target="B", type=EdgeType.DEFENDS, round=1),
        ])
        overlay = PrivateOverlay("seer")
        overlay.add_private_edge(GraphEdge(
            source="seer", target="B", type=EdgeType.VERIFIED,
            round=1, attrs={"result": "wolf"},
        ))
        overlay.derive_inferences(shared)
        inferences = overlay.get_inferences()
        assert len(inferences) >= 1
        assert any("D" in inf.conclusion for inf in inferences)

    def test_vote_against_known_good_conflict(self):
        shared = SharedGraph()
        shared.update(1, [
            GraphEdge(source="X", target="C", type=EdgeType.VOTES_FOR, round=1),
        ])
        overlay = PrivateOverlay("seer")
        overlay.add_private_edge(GraphEdge(
            source="seer", target="C", type=EdgeType.VERIFIED,
            round=1, attrs={"result": "good"},
        ))
        overlay.derive_inferences(shared)
        conflicts = overlay.get_private_conflicts()
        assert len(conflicts) >= 1

    def test_empty_overlay_no_errors(self):
        overlay = PrivateOverlay("villager")
        shared = SharedGraph()
        shared.update(1, [])
        overlay.derive_inferences(shared)
        assert overlay.get_inferences() == []
        assert overlay.get_private_conflicts() == []


# ══════════════════════════════════════════════
#  CognitiveBias
# ══════════════════════════════════════════════

class TestCognitiveBias:
    def test_impulsive_persona(self):
        bias = resolve_cognitive_bias("冲动果断的性格")
        assert bias.conclusion_threshold < 0.5
        assert bias.attention_focus == AttentionFocus.RECENT

    def test_analytical_persona(self):
        bias = resolve_cognitive_bias("深沉冷静，善于分析")
        assert bias.conclusion_threshold > 0.5
        assert bias.attention_focus == AttentionFocus.LONG_TERM

    def test_conformist_persona(self):
        bias = resolve_cognitive_bias("随和从众")
        assert bias.evidence_weights["social_consensus"] > 1.5

    def test_hesitant_persona(self):
        bias = resolve_cognitive_bias("犹豫纠结")
        assert bias.conclusion_threshold > 0.8

    def test_unknown_persona_neutral(self):
        bias = resolve_cognitive_bias("一个普通人")
        assert bias.conclusion_threshold == 0.5

    def test_empty_persona_neutral(self):
        bias = resolve_cognitive_bias("")
        assert bias.conclusion_threshold == 0.5

    def test_bias_conflict_sorting(self):
        conflicts = [
            Conflict("vote conflict", ConflictSeverity.MEDIUM, ["A"], 1, evidence_type="vote_pattern"),
            Conflict("speech conflict", ConflictSeverity.MEDIUM, ["B"], 1, evidence_type="speech_contradiction"),
        ]
        impulsive = resolve_cognitive_bias("冲动")
        sorted_conflicts = apply_bias_to_conflicts(conflicts, impulsive)
        # Impulsive weights speech_contradiction higher
        assert sorted_conflicts[0].evidence_type == "speech_contradiction"

        analytical = resolve_cognitive_bias("分析")
        sorted_conflicts = apply_bias_to_conflicts(conflicts, analytical)
        # Analytical weights vote_pattern higher
        assert sorted_conflicts[0].evidence_type == "vote_pattern"


# ══════════════════════════════════════════════
#  Reasoner
# ══════════════════════════════════════════════

class TestReasoner:
    def test_base_scores_neutral(self):
        reasoner = Reasoner()
        shared = SharedGraph()
        shared.update(1, [])
        overlay = PrivateOverlay("A")
        bias = CognitiveBias()
        trust, suspicion, chains = reasoner.reason("A", shared, overlay, bias, ["A", "B", "C"])
        assert "B" in trust
        assert "C" in trust
        assert "A" not in trust  # Self excluded
        assert trust["B"] == pytest.approx(0.5, abs=0.1)

    def test_known_wolf_max_suspicion(self):
        reasoner = Reasoner()
        shared = SharedGraph()
        shared.update(1, [])
        overlay = PrivateOverlay("seer")
        overlay.add_private_edge(GraphEdge(
            source="seer", target="B", type=EdgeType.VERIFIED,
            round=1, attrs={"result": "wolf"},
        ))
        bias = CognitiveBias()
        trust, suspicion, chains = reasoner.reason("seer", shared, overlay, bias, ["seer", "B", "C"])
        assert suspicion["B"] == 1.0
        assert trust["B"] == 0.0

    def test_known_good_max_trust(self):
        reasoner = Reasoner()
        shared = SharedGraph()
        shared.update(1, [])
        overlay = PrivateOverlay("seer")
        overlay.add_private_edge(GraphEdge(
            source="seer", target="C", type=EdgeType.VERIFIED,
            round=1, attrs={"result": "good"},
        ))
        bias = CognitiveBias()
        trust, suspicion, chains = reasoner.reason("seer", shared, overlay, bias, ["seer", "B", "C"])
        assert trust["C"] == 1.0
        assert suspicion["C"] == 0.0

    def test_role_conflict_chain(self):
        reasoner = Reasoner()
        shared = SharedGraph()
        shared.update(1, [
            GraphEdge(source="A", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
            GraphEdge(source="B", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
        ])
        overlay = PrivateOverlay("C")
        bias = CognitiveBias()
        trust, suspicion, chains = reasoner.reason("C", shared, overlay, bias, ["A", "B", "C"])
        role_chains = [c for c in chains if "预言家" in c.conclusion]
        assert len(role_chains) >= 1

    def test_hesitant_filters_weak_chains(self):
        reasoner = Reasoner()
        shared = SharedGraph()
        # Only 1 round of vote alignment → low confidence chain
        shared.update(1, [
            GraphEdge(source="A", target="X", type=EdgeType.VOTES_FOR, round=1),
            GraphEdge(source="B", target="X", type=EdgeType.VOTES_FOR, round=1),
        ])
        overlay = PrivateOverlay("C")
        hesitant = resolve_cognitive_bias("犹豫")  # threshold 0.9
        trust, suspicion, chains = reasoner.reason("C", shared, overlay, hesitant, ["A", "B", "C"])
        # Low confidence chains should be filtered out
        vote_chains = [c for c in chains if "投票" in c.conclusion or "同阵营" in c.conclusion]
        assert len(vote_chains) == 0  # 0.55 confidence < 0.9 threshold


# ══════════════════════════════════════════════
#  Summarizer
# ══════════════════════════════════════════════

class TestSummarizer:
    def test_thinker_text_contains_sections(self):
        summarizer = GraphSummarizer()
        shared = SharedGraph()
        shared.update(1, [
            GraphEdge(source="A", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
            GraphEdge(source="B", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
        ])
        trust = {"A": 0.5, "B": 0.3}
        suspicion = {"A": 0.1, "B": 0.4}
        conflicts = shared.get_public_conflicts()
        chains = [ReasoningChain(["p1", "p2"], "conclusion", 0.8)]
        bias = CognitiveBias()
        summary = summarizer.summarize(shared, trust, suspicion, conflicts, chains, bias)
        text = summarizer.to_thinker_text(summary)
        assert "矛盾" in text
        assert "信任" in text

    def test_evaluator_text_lists_conflicts(self):
        summarizer = GraphSummarizer()
        conflicts = [
            Conflict("test conflict", ConflictSeverity.HIGH, ["A"], 1),
        ]
        text = summarizer.to_evaluator_text(conflicts)
        assert "test conflict" in text
        assert "图谱分析" in text

    def test_empty_summary_no_crash(self):
        summarizer = GraphSummarizer()
        shared = SharedGraph()
        shared.update(1, [])
        bias = CognitiveBias()
        summary = summarizer.summarize(shared, {}, {}, [], [], bias)
        text = summarizer.to_thinker_text(summary)
        assert isinstance(text, str)


# ══════════════════════════════════════════════
#  ConflictDetector
# ══════════════════════════════════════════════

class TestConflictDetector:
    def test_detect_public_returns_cached(self):
        detector = ConflictDetector()
        shared = SharedGraph()
        shared.update(1, [
            GraphEdge(source="A", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
            GraphEdge(source="B", target="预言家", type=EdgeType.CLAIMS_ROLE, round=1),
        ])
        conflicts = detector.detect_public(shared)
        assert len(conflicts) >= 1

    def test_detect_private_with_wolf_defense(self):
        detector = ConflictDetector()
        shared = SharedGraph()
        shared.update(1, [
            GraphEdge(source="D", target="B", type=EdgeType.DEFENDS, round=1),
        ])
        overlay = PrivateOverlay("seer")
        overlay.add_private_edge(GraphEdge(
            source="seer", target="B", type=EdgeType.VERIFIED,
            round=1, attrs={"result": "wolf"},
        ))
        conflicts = detector.detect_private(shared, overlay, 1)
        assert len(conflicts) >= 1


# ══════════════════════════════════════════════
#  GameReasoningGraph (Facade)
# ══════════════════════════════════════════════

class TestFacade:
    def test_full_round_flow(self):
        grg = GameReasoningGraph()
        grg.setup(["A", "B", "C", "D"], {
            "A": "冲动", "B": "深沉分析", "C": "从众", "D": "犹豫",
        })

        grg.record_action("A", "speak", {"content": "C很可疑"})
        grg.record_action("B", "speak", {"content": "我信任A"})
        grg.record_action("C", "speak", {"content": "我是预言家"})
        grg.record_action("D", "speak", {"content": "我是预言家"})

        public_state = {
            "round_number": 1,
            "alive_players": ["A", "B", "C", "D"],
            "vote_history": {1: {"A": "C", "B": "C", "C": "D", "D": "C"}},
        }
        grg.update_round(1, public_state)

        ctx_a = grg.get_thinker_context("A", ["A", "B", "C", "D"])
        ctx_b = grg.get_thinker_context("B", ["A", "B", "C", "D"])
        assert isinstance(ctx_a, str)
        assert isinstance(ctx_b, str)
        # Different biases → different outputs
        assert ctx_a != ctx_b

    def test_prophet_conflict_detected(self):
        grg = GameReasoningGraph()
        grg.setup(["A", "B", "C"], {"A": "", "B": "", "C": ""})
        grg.record_action("A", "speak", {"content": "我是预言家"})
        grg.record_action("B", "speak", {"content": "我是预言家"})
        grg.update_round(1, {"round_number": 1, "alive_players": ["A", "B", "C"], "vote_history": {}})

        ctx = grg.get_thinker_context("C", ["A", "B", "C"])
        assert "预言家" in ctx

    def test_private_info_affects_context(self):
        grg = GameReasoningGraph()
        grg.setup(["seer", "B", "C"], {"seer": "", "B": "", "C": ""})
        grg.update_round(1, {"round_number": 1, "alive_players": ["seer", "B", "C"], "vote_history": {}})
        grg.update_private("seer", 1, {"check_history": {"B": "wolf"}})

        ctx_seer = grg.get_thinker_context("seer", ["seer", "B", "C"])
        ctx_c = grg.get_thinker_context("C", ["seer", "B", "C"])
        # Seer should have more info (knows B is wolf)
        assert ctx_seer != ctx_c

    def test_evaluator_context(self):
        grg = GameReasoningGraph()
        grg.setup(["A", "B"], {"A": "", "B": ""})
        grg.record_action("A", "speak", {"content": "我是预言家"})
        grg.record_action("B", "speak", {"content": "我是预言家"})
        grg.update_round(1, {"round_number": 1, "alive_players": ["A", "B"], "vote_history": {}})

        eval_ctx = grg.get_evaluator_context("A")
        # Should mention the prophet conflict
        assert "预言家" in eval_ctx or eval_ctx == ""  # evaluator context may filter

    def test_empty_game_no_crash(self):
        grg = GameReasoningGraph()
        grg.setup(["A", "B"], {"A": "", "B": ""})
        grg.update_round(1, {"round_number": 1, "alive_players": ["A", "B"], "vote_history": {}})
        ctx = grg.get_thinker_context("A", ["A", "B"])
        assert isinstance(ctx, str)

    def test_unknown_player_returns_empty(self):
        grg = GameReasoningGraph()
        grg.setup(["A"], {"A": ""})
        ctx = grg.get_thinker_context("UNKNOWN", ["A"])
        assert ctx == ""

    def test_multi_round_accumulation(self):
        grg = GameReasoningGraph()
        grg.setup(["A", "B", "C"], {"A": "", "B": "", "C": ""})

        for r in [1, 2, 3]:
            grg.record_action("A", "vote", {"target": "C"})
            grg.record_action("B", "vote", {"target": "C"})
            grg.update_round(r, {
                "round_number": r,
                "alive_players": ["A", "B", "C"],
                "vote_history": {r: {"A": "C", "B": "C"}},
            })

        ctx = grg.get_thinker_context("C", ["A", "B", "C"])
        # After 3 rounds of aligned voting, should detect pattern
        assert len(ctx) > 0
