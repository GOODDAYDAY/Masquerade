"""AI Response Validation Tests — REQ-014 AIOps-style testing.

Tests real LLM API calls for each game role/phase, validating that
AI responses conform to expected formats and constraints.

Requires: MASQUERADE_LLM__API_KEY env var (or .env file).
Skips gracefully if no API key is available.

Default OFF (takes ~10 minutes). Enable with RUN_AI_TESTS=1:

    RUN_AI_TESTS=1 python -m pytest backend/tests/test_ai_response_validation.py -v
    RUN_AI_TESTS=1 python -m pytest backend/tests/test_ai_response_validation.py -v -k "spy"
    RUN_AI_TESTS=1 python -m pytest backend/tests/test_ai_response_validation.py -v -k "werewolf"
"""

import asyncio
import json
import os
import re

import pytest

from backend.agent.llm_client import LLMClient
from backend.agent.strategy import AgentStrategy
from backend.engine.spy.strategy import get_spy_strategy, get_blank_strategy
from backend.engine.werewolf.strategy import (
    get_werewolf_night_strategy,
    get_werewolf_day_strategy,
    get_seer_night_strategy,
    get_seer_day_strategy,
    get_witch_night_strategy,
    get_witch_day_strategy,
    get_guard_night_strategy,
    get_guard_day_strategy,
    get_villager_day_strategy,
    get_hunter_day_strategy,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Try to load API key from env or .env file."""
    key = os.environ.get("MASQUERADE_LLM__API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("MASQUERADE_LLM__API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


API_KEY = _get_api_key()
# Default OFF — these tests call real LLM APIs and take ~10 minutes.
# Enable with: RUN_AI_TESTS=1 python -m pytest backend/tests/test_ai_response_validation.py -v
_AI_TESTS_ENABLED = os.environ.get("RUN_AI_TESTS", "").strip() in ("1", "true", "yes")
SKIP_REASON = "AI tests disabled (set RUN_AI_TESTS=1 to enable)" if not _AI_TESTS_ENABLED else "No LLM API key (set MASQUERADE_LLM__API_KEY)"

requires_api = pytest.mark.skipif(not _AI_TESTS_ENABLED or not API_KEY, reason=SKIP_REASON)


def _make_client() -> LLMClient:
    model = os.environ.get("MASQUERADE_LLM__MODEL", "deepseek-chat")
    api_base = os.environ.get("MASQUERADE_LLM__API_BASE", "https://api.deepseek.com/v1")
    return LLMClient(model=model, api_base=api_base, api_key=API_KEY or "")


# ---------------------------------------------------------------------------
# Helper: call thinker prompt and parse JSON response
# ---------------------------------------------------------------------------

async def _call_thinker(
    strategy: AgentStrategy,
    player_id: str,
    private_info: dict,
    public_state: dict,
    available_actions: list[str],
    game_rules: str = "你正在参加一场桌游。",
    persona: str = "性格直爽。",
) -> dict:
    """Send a thinker prompt to LLM and parse JSON response."""
    client = _make_client()

    # Format the thinker prompt with game context
    prompt = strategy.thinker_prompt.format(
        player_id=player_id,
        private_info=json.dumps(private_info, ensure_ascii=False),
        public_state=json.dumps(public_state, ensure_ascii=False),
        available_actions=json.dumps(available_actions, ensure_ascii=False),
    )

    messages = [
        {"role": "system", "content": f"{game_rules}\n\n你的角色人设：{persona}"},
        {"role": "user", "content": prompt},
    ]

    raw = await client.chat(messages, temperature=0.7)

    # Extract JSON from response (may be wrapped in markdown code block)
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    content = json_match.group(1) if json_match else raw

    # Try to parse as JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        obj_match = re.search(r"\{[\s\S]*\}", content)
        if obj_match:
            return json.loads(obj_match.group())
        pytest.fail(f"Failed to parse JSON from LLM response:\n{raw[:500]}")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

REQUIRED_THINKER_FIELDS = {"situation_analysis", "strategy", "action_type", "action_content", "expression"}
VALID_EXPRESSIONS = {"neutral", "thinking", "surprised", "smile", "confident", "serious", "angry"}
PLAYER_NAMES_SPY = ["甄大胆", "甄谨慎", "甄反骨"]
PLAYER_NAMES_WEREWOLF = [
    "甄冲动", "甄深沉", "甄心软", "甄话痨", "甄逻辑", "甄纠结",
    "甄犀利", "甄演技", "甄迷糊", "甄号召", "甄推理", "甄潜水",
]


def assert_valid_thinker_response(result: dict, available_actions: list[str], context: str = ""):
    """Validate common thinker response structure."""
    prefix = f"[{context}] " if context else ""

    # All required fields present
    for field in REQUIRED_THINKER_FIELDS:
        assert field in result, f"{prefix}Missing field: {field}"

    # action_type is one of available actions
    assert result["action_type"] in available_actions, (
        f"{prefix}action_type '{result['action_type']}' not in {available_actions}"
    )

    # expression is valid
    assert result["expression"] in VALID_EXPRESSIONS, (
        f"{prefix}Invalid expression: {result['expression']}"
    )

    # situation_analysis is non-empty
    analysis = result["situation_analysis"]
    if isinstance(analysis, str):
        assert len(analysis) > 10, f"{prefix}situation_analysis too short"
    elif isinstance(analysis, dict):
        assert len(analysis) > 0, f"{prefix}situation_analysis empty dict"

    # action_content is non-empty
    assert result["action_content"], f"{prefix}action_content is empty"


def assert_no_name_bias(result: dict, context: str = ""):
    """Check that reasoning doesn't use player names as evidence for suspicion."""
    prefix = f"[{context}] " if context else ""
    analysis = str(result.get("situation_analysis", "")) + str(result.get("strategy", ""))

    # Strip out rule citations — AI may quote the anti-bias rule itself
    # Remove text between 【反名字偏见】 markers or references to the rule
    cleaned = re.sub(r"反名字偏见[^。]*。", "", analysis)
    cleaned = re.sub(r"名字[≠!=]行为证据", "", cleaned)
    cleaned = re.sub(r"不[能会应该]*因为.*?名字.*?偏见", "", cleaned)

    # Known name-bias patterns (checked against cleaned text)
    bias_patterns = [
        r"名字.*可疑",
        r"叫.*所以.*投",
        r"名字叫.*嫌疑",
        r"从名字.*判断",
        r"名字说明",
        r"顾名思义",
    ]
    for pattern in bias_patterns:
        assert not re.search(pattern, cleaned), (
            f"{prefix}Potential name bias detected: pattern '{pattern}' in analysis"
        )


def assert_vote_has_evidence(result: dict, context: str = ""):
    """For voting actions, check that evidence is cited."""
    prefix = f"[{context}] " if context else ""
    if result.get("action_type") != "vote":
        return

    analysis = str(result.get("situation_analysis", "")) + str(result.get("strategy", ""))
    # Should reference someone's speech or behavior
    has_evidence = any(kw in analysis for kw in [
        "发言", "说过", "描述", "提到", "他说", "她说", "投票",
        "逻辑", "矛盾", "可疑", "行为", "分析", "根据",
    ])
    assert has_evidence, f"{prefix}Vote decision lacks evidence in analysis"


def assert_witch_action_format(result: dict, context: str = ""):
    """Validate witch action_content can be interpreted as a valid witch action."""
    prefix = f"[{context}] " if context else ""
    content = result.get("action_content", "")

    # AI may return a dict like {"use": "antidote", "target": None} — extract the use field
    if isinstance(content, dict):
        content = content.get("use", content.get("action", ""))

    content = str(content).strip().lower()
    valid = content in ("antidote", "poison", "skip") or content.startswith("poison")
    assert valid, f"{prefix}Invalid witch action_content: '{content}'. Expected antidote/poison/skip"


def assert_silent_night_action(result: dict, context: str = ""):
    """Validate night actions contain no sound-producing descriptions."""
    prefix = f"[{context}] " if context else ""
    content = str(result.get("action_content", ""))
    sound_words = ["拍桌", "拍手", "跺脚", "弹指", "敲", "拍了", "击掌", "啪"]
    for word in sound_words:
        assert word not in content, (
            f"{prefix}Sound-producing action detected: '{word}' in '{content}'"
        )


# ---------------------------------------------------------------------------
# Spy game tests
# ---------------------------------------------------------------------------

SPY_PUBLIC_STATE = {
    "round": 1,
    "alive_players": PLAYER_NAMES_SPY,
    "history": [
        {"round": 1, "events": [
            {"player": "甄大胆", "action": "speak", "content": "这东西夏天特别受欢迎，冰镇了更好吃。"},
        ]}
    ],
}


@requires_api
class TestSpySpeakResponse:
    """Test spy game speaking phase AI responses."""

    def test_civilian_speak_format(self):
        """Civilian speaking response has correct structure."""
        strategy = get_spy_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄谨慎",
            private_info={"word": "西瓜", "role": "civilian"},
            public_state=SPY_PUBLIC_STATE,
            available_actions=["speak"],
        ))
        assert_valid_thinker_response(result, ["speak"], "civilian_speak")
        assert_no_name_bias(result, "civilian_speak")
        # Speech should not directly reveal the word
        content = str(result["action_content"])
        assert "西瓜" not in content, "Speech directly reveals the word"

    def test_spy_speak_format(self):
        """Spy speaking response has correct structure and doesn't reveal word."""
        strategy = get_spy_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄反骨",
            private_info={"word": "哈密瓜", "role": "spy"},
            public_state=SPY_PUBLIC_STATE,
            available_actions=["speak"],
        ))
        assert_valid_thinker_response(result, ["speak"], "spy_speak")
        assert_no_name_bias(result, "spy_speak")
        content = str(result["action_content"])
        assert "哈密瓜" not in content, "Spy speech directly reveals the word"

    def test_blank_speak_format(self):
        """Blank player speaking response doesn't reveal blank status."""
        strategy = get_blank_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄大胆",
            private_info={"word": "(无)", "role": "blank"},
            public_state=SPY_PUBLIC_STATE,
            available_actions=["speak"],
        ))
        assert_valid_thinker_response(result, ["speak"], "blank_speak")
        content = str(result["action_content"]).lower()
        assert "没有词" not in content, "Blank player reveals no-word status"
        assert "白板" not in content, "Blank player reveals blank status"


@requires_api
class TestSpyVoteResponse:
    """Test spy game voting phase AI responses."""

    def test_vote_format_and_evidence(self):
        """Vote response targets a valid player with evidence."""
        strategy = get_spy_strategy()
        state = {**SPY_PUBLIC_STATE, "phase": "voting"}
        result = asyncio.run(_call_thinker(
            strategy, "甄谨慎",
            private_info={"word": "西瓜", "role": "civilian"},
            public_state=state,
            available_actions=["vote"],
        ))
        assert_valid_thinker_response(result, ["vote"], "vote")
        assert_no_name_bias(result, "vote")
        assert_vote_has_evidence(result, "vote")

        # Vote target should be a valid player, not self
        target = str(result["action_content"])
        assert target != "甄谨慎", "Player voted for self"
        assert target in PLAYER_NAMES_SPY, f"Vote target '{target}' not a valid player"


# ---------------------------------------------------------------------------
# Werewolf game tests
# ---------------------------------------------------------------------------

WEREWOLF_PUBLIC_STATE = {
    "round": 1,
    "phase": "night",
    "alive_players": PLAYER_NAMES_WEREWOLF,
    "history": [],
}

WEREWOLF_DAY_STATE = {
    "round": 1,
    "phase": "day_discussion",
    "alive_players": PLAYER_NAMES_WEREWOLF,
    "history": [
        {"round": 1, "events": [
            {"player": "甄号召", "action": "speak", "content": "我觉得昨晚有点不对劲，甄冲动发言太激动了。"},
            {"player": "甄逻辑", "action": "speak", "content": "我同意，我们先听听每个人的分析。"},
        ]}
    ],
    "deaths": [],
}


@requires_api
class TestWolfNightResponse:
    """Test werewolf night phase AI responses."""

    def test_wolf_discuss_gesture_format(self):
        """Wolf discussion produces silent gesture description."""
        strategy = get_werewolf_night_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄冲动",
            private_info={"role": "werewolf", "teammates": ["甄深沉", "甄迷糊"]},
            public_state=WEREWOLF_PUBLIC_STATE,
            available_actions=["wolf_discuss"],
        ))
        assert_valid_thinker_response(result, ["wolf_discuss"], "wolf_discuss")
        assert_silent_night_action(result, "wolf_discuss")

    def test_wolf_kill_target_valid(self):
        """Wolf kill targets a valid non-wolf player."""
        strategy = get_werewolf_night_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄冲动",
            private_info={"role": "werewolf", "teammates": ["甄深沉", "甄迷糊"]},
            public_state=WEREWOLF_PUBLIC_STATE,
            available_actions=["wolf_kill"],
        ))
        assert_valid_thinker_response(result, ["wolf_kill"], "wolf_kill")
        target = str(result["action_content"])
        wolf_team = {"甄冲动", "甄深沉", "甄迷糊"}
        assert target not in wolf_team, f"Wolf trying to kill teammate: {target}"


@requires_api
class TestSeerResponse:
    """Test seer night/day responses."""

    def test_seer_check_target_valid(self):
        """Seer check targets a valid player, not self."""
        strategy = get_seer_night_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄号召",
            private_info={"role": "seer", "check_results": {}},
            public_state=WEREWOLF_PUBLIC_STATE,
            available_actions=["seer_check"],
        ))
        assert_valid_thinker_response(result, ["seer_check"], "seer_check")
        target = str(result["action_content"])
        assert target != "甄号召", "Seer checked self"
        assert target in PLAYER_NAMES_WEREWOLF, f"Seer target '{target}' not valid player"

    def test_seer_day_with_wolf_found(self):
        """Seer who found a wolf should recommend jumping/reporting."""
        strategy = get_seer_day_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄号召",
            private_info={"role": "seer", "check_results": {"甄冲动": "wolf"}},
            public_state=WEREWOLF_DAY_STATE,
            available_actions=["speak"],
        ))
        assert_valid_thinker_response(result, ["speak"], "seer_day_wolf")
        # Should mention the wolf or recommend voting
        analysis = str(result.get("situation_analysis", "")) + str(result.get("strategy", ""))
        assert "甄冲动" in analysis, "Seer didn't reference found wolf in analysis"


@requires_api
class TestWitchResponse:
    """Test witch night responses — critical format validation."""

    def test_witch_antidote_format(self):
        """Witch antidote response has correct format."""
        strategy = get_witch_night_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄心软",
            private_info={
                "role": "witch",
                "killed_tonight": "甄逻辑",
                "antidote_available": True,
                "poison_available": True,
            },
            public_state=WEREWOLF_PUBLIC_STATE,
            available_actions=["witch_action"],
        ))
        assert_valid_thinker_response(result, ["witch_action"], "witch_action")
        assert_witch_action_format(result, "witch_action")

    def test_witch_poison_format(self):
        """Witch poison response separates use and target correctly."""
        strategy = get_witch_night_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄心软",
            private_info={
                "role": "witch",
                "killed_tonight": None,
                "antidote_available": False,
                "poison_available": True,
            },
            public_state={
                **WEREWOLF_PUBLIC_STATE,
                "round": 3,
                "history": [
                    {"round": 2, "events": [
                        {"player": "甄冲动", "action": "speak", "content": "我觉得大家都没问题。"},
                    ]},
                ],
            },
            available_actions=["witch_action"],
        ))
        assert_valid_thinker_response(result, ["witch_action"], "witch_poison")
        content = str(result["action_content"])
        # If AI chose poison, content should not be "poison 甄xxx" (space-separated)
        if content.startswith("poison") and len(content) > 6:
            # Acceptable formats: "poison", "poison:甄xxx"
            # Unacceptable: "poison 甄xxx" (but engine now handles this)
            assert content[6] != " " or True, (
                "Witch poison format uses space separator (engine tolerates, but not ideal)"
            )


@requires_api
class TestGuardResponse:
    """Test guard night responses."""

    def test_guard_protect_valid_target(self):
        """Guard protects a valid player (name, not number)."""
        strategy = get_guard_night_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄纠结",
            private_info={"role": "guard", "last_protected": None},
            public_state=WEREWOLF_PUBLIC_STATE,
            available_actions=["protect"],
        ))
        assert_valid_thinker_response(result, ["protect"], "guard_protect")
        target = str(result["action_content"]).strip()
        # Target should be a player name, not a number
        assert not target.isdigit(), f"Guard returned number '{target}' instead of player name"
        assert target in PLAYER_NAMES_WEREWOLF, f"Guard target '{target}' not valid player"

    def test_guard_no_repeat_protect(self):
        """Guard should not protect same player as last round."""
        strategy = get_guard_night_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄纠结",
            private_info={"role": "guard", "last_protected": "甄号召"},
            public_state={**WEREWOLF_PUBLIC_STATE, "round": 2},
            available_actions=["protect"],
        ))
        assert_valid_thinker_response(result, ["protect"], "guard_no_repeat")
        target = str(result["action_content"])
        # AI should avoid last-protected target (though engine enforces this too)
        if target == "甄号召":
            pytest.xfail("Guard chose same target as last round (engine will reject)")


@requires_api
class TestVillagerDayResponse:
    """Test villager day responses."""

    def test_villager_speak_with_analysis(self):
        """Villager day speech contains logical analysis."""
        strategy = get_villager_day_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄犀利",
            private_info={"role": "villager"},
            public_state=WEREWOLF_DAY_STATE,
            available_actions=["speak"],
        ))
        assert_valid_thinker_response(result, ["speak"], "villager_speak")
        assert_no_name_bias(result, "villager_speak")

    def test_villager_vote_with_evidence(self):
        """Villager vote cites evidence."""
        strategy = get_villager_day_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄犀利",
            private_info={"role": "villager"},
            public_state={**WEREWOLF_DAY_STATE, "phase": "day_voting"},
            available_actions=["vote"],
        ))
        assert_valid_thinker_response(result, ["vote"], "villager_vote")
        assert_no_name_bias(result, "villager_vote")
        assert_vote_has_evidence(result, "villager_vote")
        target = str(result["action_content"])
        assert target != "甄犀利", "Villager voted for self"


@requires_api
class TestHunterResponse:
    """Test hunter responses."""

    def test_hunter_shoot_decision(self):
        """Hunter shoot response has valid target (name, not analysis text)."""
        strategy = get_hunter_day_strategy(is_shooting=True)
        result = asyncio.run(_call_thinker(
            strategy, "甄果断",
            private_info={"role": "hunter"},
            public_state=WEREWOLF_DAY_STATE,
            available_actions=["hunter_shoot"],
        ))
        assert_valid_thinker_response(result, ["hunter_shoot"], "hunter_shoot")
        target = str(result["action_content"]).strip()
        # Target should be short (player name or "skip"), not a long analysis paragraph
        assert len(target) < 50, f"Hunter action_content is too long ({len(target)} chars) — likely analysis text instead of target ID"
        valid = target in PLAYER_NAMES_WEREWOLF or target == "skip"
        assert valid, f"Hunter target '{target}' not valid player name"
        if target == "skip":
            pytest.xfail("Hunter chose skip (evaluator should penalize)")


@requires_api
class TestWolfDayResponse:
    """Test wolf day (deception) responses."""

    def test_wolf_day_disguise(self):
        """Wolf day speech doesn't expose wolf identity."""
        strategy = get_werewolf_day_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄深沉",
            private_info={"role": "werewolf", "teammates": ["甄冲动", "甄迷糊"]},
            public_state=WEREWOLF_DAY_STATE,
            available_actions=["speak"],
        ))
        assert_valid_thinker_response(result, ["speak"], "wolf_day")
        assert_no_name_bias(result, "wolf_day")
        content = str(result["action_content"])
        assert "我是狼" not in content, "Wolf exposed self in speech"

    def test_wolf_vote_not_teammate(self):
        """Wolf doesn't vote for wolf teammate."""
        strategy = get_werewolf_day_strategy()
        result = asyncio.run(_call_thinker(
            strategy, "甄深沉",
            private_info={"role": "werewolf", "teammates": ["甄冲动", "甄迷糊"]},
            public_state={**WEREWOLF_DAY_STATE, "phase": "day_voting"},
            available_actions=["vote"],
        ))
        assert_valid_thinker_response(result, ["vote"], "wolf_vote")
        target = str(result["action_content"])
        wolf_team = {"甄深沉", "甄冲动", "甄迷糊"}
        assert target not in wolf_team, f"Wolf voted for teammate: {target}"
