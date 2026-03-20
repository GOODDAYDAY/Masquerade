"""EventExtractor — converts engine events to graph edges.

Phase 1: Pure programmatic extraction (votes, deaths, skills) — zero LLM cost.
Phase 2 (future): LLM-assisted extraction for speech semantic analysis.
"""

import re

from backend.reasoning.models import EdgeType, GraphEdge


# Keywords that indicate role claims in speech content
_ROLE_CLAIM_PATTERNS: list[tuple[str, str]] = [
    (r"我是预言家", "预言家"),
    (r"我是先知", "预言家"),
    (r"我是seer", "预言家"),
    (r"预言家.*是我", "预言家"),
    (r"我是女巫", "女巫"),
    (r"我是witch", "女巫"),
    (r"我是猎人", "猎人"),
    (r"我是hunter", "猎人"),
    (r"我是守卫", "守卫"),
    (r"我是guard", "守卫"),
]

# Keywords that indicate accusation in speech
_ACCUSE_KEYWORDS: list[str] = [
    "可疑", "怀疑", "是狼", "狼人", "有问题", "不对劲",
    "说谎", "骗人", "假的", "冒充", "伪装",
]

# Keywords that indicate defense in speech
_DEFEND_KEYWORDS: list[str] = [
    "可信", "信任", "好人", "没问题", "清白", "相信",
    "支持", "赞同", "同意", "拉票",
]


class EventExtractor:
    """Converts engine data to graph edges. Programmatic, no LLM calls."""

    # ══════════════════════════════════════════════
    #  Public orchestration methods
    # ══════════════════════════════════════════════

    def extract_round_events(
        self,
        round_number: int,
        public_state: dict,
        round_actions: list[dict],
    ) -> list[GraphEdge]:
        """Extract all public relations from one round of engine data."""
        edges: list[GraphEdge] = []
        edges.extend(self._extract_votes(round_number, public_state))
        edges.extend(self._extract_deaths(round_number, public_state))
        edges.extend(self._extract_speech_relations(round_number, round_actions))
        return edges

    def extract_private_events(
        self,
        player_id: str,
        round_number: int,
        private_info: dict,
    ) -> list[GraphEdge]:
        """Extract private relations from a player's private info."""
        edges: list[GraphEdge] = []
        edges.extend(self._extract_verifications(player_id, round_number, private_info))
        edges.extend(self._extract_teammate_info(player_id, round_number, private_info))
        return edges

    # ══════════════════════════════════════════════
    #  Private step methods — public events
    # ══════════════════════════════════════════════

    def _extract_votes(self, round_number: int, public_state: dict) -> list[GraphEdge]:
        """Extract VOTES_FOR edges from public_state.vote_history."""
        edges: list[GraphEdge] = []
        vote_history = public_state.get("vote_history", {})
        round_votes = vote_history.get(str(round_number), vote_history.get(round_number, {}))
        for voter, target in round_votes.items():
            if voter and target:
                edges.append(GraphEdge(
                    source=str(voter),
                    target=str(target),
                    type=EdgeType.VOTES_FOR,
                    round=round_number,
                ))
        return edges

    def _extract_deaths(self, round_number: int, public_state: dict) -> list[GraphEdge]:
        """Extract KILLED edges from death information."""
        edges: list[GraphEdge] = []
        night_deaths = public_state.get("night_deaths", [])
        for dead in night_deaths:
            edges.append(GraphEdge(
                source="system",
                target=str(dead),
                type=EdgeType.KILLED,
                round=round_number,
                attrs={"cause": "night_kill"},
            ))

        eliminated = public_state.get("eliminated_this_round", "")
        if eliminated:
            edges.append(GraphEdge(
                source="system",
                target=str(eliminated),
                type=EdgeType.KILLED,
                round=round_number,
                attrs={"cause": "vote_out"},
            ))
        return edges

    def _extract_speech_relations(
        self, round_number: int, round_actions: list[dict],
    ) -> list[GraphEdge]:
        """Extract ACCUSES, DEFENDS, CLAIMS_ROLE from speech actions."""
        edges: list[GraphEdge] = []
        player_ids = self._collect_player_ids(round_actions)

        for action_data in round_actions:
            action_type = action_data.get("type", "")
            if action_type != "speak":
                continue

            speaker = action_data.get("player_id", "")
            content = action_data.get("payload", {}).get("content", "")
            if not speaker or not content:
                continue

            edges.extend(self._detect_role_claims(speaker, content, round_number))
            edges.extend(self._detect_accusations(speaker, content, round_number, player_ids))
            edges.extend(self._detect_defenses(speaker, content, round_number, player_ids))

        return edges

    def _detect_role_claims(
        self, speaker: str, content: str, round_number: int,
    ) -> list[GraphEdge]:
        """Detect role claims via keyword pattern matching."""
        edges: list[GraphEdge] = []
        for pattern, role in _ROLE_CLAIM_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                edges.append(GraphEdge(
                    source=speaker,
                    target=role,
                    type=EdgeType.CLAIMS_ROLE,
                    round=round_number,
                ))
                break
        return edges

    def _detect_accusations(
        self,
        speaker: str,
        content: str,
        round_number: int,
        player_ids: list[str],
    ) -> list[GraphEdge]:
        """Detect accusations by checking if accusation keywords co-occur with player names."""
        edges: list[GraphEdge] = []
        has_accuse_keyword = any(kw in content for kw in _ACCUSE_KEYWORDS)
        if not has_accuse_keyword:
            return edges

        for pid in player_ids:
            if pid == speaker:
                continue
            if pid in content:
                edges.append(GraphEdge(
                    source=speaker,
                    target=pid,
                    type=EdgeType.ACCUSES,
                    round=round_number,
                ))
        return edges

    def _detect_defenses(
        self,
        speaker: str,
        content: str,
        round_number: int,
        player_ids: list[str],
    ) -> list[GraphEdge]:
        """Detect defenses by checking if defense keywords co-occur with player names."""
        edges: list[GraphEdge] = []
        has_defend_keyword = any(kw in content for kw in _DEFEND_KEYWORDS)
        if not has_defend_keyword:
            return edges

        for pid in player_ids:
            if pid == speaker:
                continue
            if pid in content:
                edges.append(GraphEdge(
                    source=speaker,
                    target=pid,
                    type=EdgeType.DEFENDS,
                    round=round_number,
                ))
        return edges

    # ══════════════════════════════════════════════
    #  Private step methods — private events
    # ══════════════════════════════════════════════

    def _extract_verifications(
        self, player_id: str, round_number: int, private_info: dict,
    ) -> list[GraphEdge]:
        """Extract VERIFIED edges from seer's private info."""
        edges: list[GraphEdge] = []
        check_history = private_info.get("check_history", {})
        for target, result in check_history.items():
            edges.append(GraphEdge(
                source=player_id,
                target=str(target),
                type=EdgeType.VERIFIED,
                round=round_number,
                attrs={"result": result},
            ))
        return edges

    def _extract_teammate_info(
        self, player_id: str, round_number: int, private_info: dict,
    ) -> list[GraphEdge]:
        """Extract TEAMMATE edges from werewolf's private info."""
        edges: list[GraphEdge] = []
        teammates = private_info.get("teammates", [])
        for teammate in teammates:
            if str(teammate) != player_id:
                edges.append(GraphEdge(
                    source=player_id,
                    target=str(teammate),
                    type=EdgeType.TEAMMATE,
                    round=round_number,
                ))
        return edges

    # ══════════════════════════════════════════════
    #  Utility helpers
    # ══════════════════════════════════════════════

    def _collect_player_ids(self, round_actions: list[dict]) -> list[str]:
        """Collect unique player IDs from action data."""
        ids = set()
        for action_data in round_actions:
            pid = action_data.get("player_id", "")
            if pid and pid != "system":
                ids.add(pid)
        return list(ids)
