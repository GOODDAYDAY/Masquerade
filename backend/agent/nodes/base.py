"""Shared utilities for all agent decision nodes.

Provides:
- build_node_messages(): consistent LLM message assembly
- parse_llm_json(): markdown-fence-aware JSON parsing
- tools_schema helpers: find_tool(), is_player_field(), has_speech_field()
- Shared constants for field detection heuristics
"""

import json

from backend.agent.state import AgentState


# ══════════════════════════════════════════════
#  Shared constants — field detection heuristics
# ══════════════════════════════════════════════

# Heuristics for identifying player-target fields
TARGET_NAME_HINTS = ("target", "player_id")
TARGET_DESC_HINTS = ("玩家", "player", "ID")

# Heuristics for identifying speech/content fields worth LLM polishing or scoring
SPEECH_DESC_HINTS = ("发言", "内容", "说", "看法", "推理", "遗言", "动作", "手势")


# ══════════════════════════════════════════════
#  JSON parsing — shared across all nodes
# ══════════════════════════════════════════════

def parse_llm_json(text: str) -> dict:
    """Extract and parse JSON from LLM response, handling markdown fences.

    Strips ```json ... ``` or ``` ... ``` wrappers before parsing.
    Raises json.JSONDecodeError if parsing fails.
    """
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


# ══════════════════════════════════════════════
#  tools_schema helpers — shared across nodes
# ══════════════════════════════════════════════

def find_tool(tools_schema: list[dict], action_type: str) -> dict | None:
    """Find the tool definition matching the action type."""
    for tool in tools_schema:
        if tool.get("function", {}).get("name") == action_type:
            return tool
    return None


def is_player_field(field_name: str, description: str) -> bool:
    """Heuristic: does this field represent a player target?"""
    if any(hint in field_name.lower() for hint in TARGET_NAME_HINTS):
        return True
    if any(hint in description for hint in TARGET_DESC_HINTS):
        return True
    return False


def has_speech_field(action_type: str, tools_schema: list[dict]) -> bool:
    """Check if an action type has a speech/content field worth LLM processing."""
    tool = find_tool(tools_schema, action_type)
    if not tool:
        return False
    params = tool.get("function", {}).get("parameters", {})
    for field_name in params.get("required", []):
        prop = params.get("properties", {}).get(field_name, {})
        desc = prop.get("description", "")
        if any(hint in desc for hint in SPEECH_DESC_HINTS):
            return True
    return False


def find_speech_field(action_type: str, tools_schema: list[dict]) -> str | None:
    """Find the text content field name that benefits from LLM polishing.

    Returns None if no speech field found — caller should skip LLM.
    """
    tool = find_tool(tools_schema, action_type)
    if not tool:
        return None
    params = tool.get("function", {}).get("parameters", {})
    for field_name in params.get("required", []):
        prop = params.get("properties", {}).get(field_name, {})
        desc = prop.get("description", "")
        if any(hint in desc for hint in SPEECH_DESC_HINTS):
            return field_name
    return None


# ══════════════════════════════════════════════
#  LLM message assembly
# ══════════════════════════════════════════════

def build_node_messages(
    state: AgentState,
    user_prompt: str,
    *,
    include_memory: bool = True,
    include_public_state: bool = True,
    include_private_info: bool = True,
) -> list[dict]:
    """Build LLM messages with full game context.

    Structure:
      1. System message: game_rules + persona
      2. Memory context messages (if include_memory)
      3. User message: node-specific prompt + game state appendix
    """
    messages: list[dict] = []

    # System message: game rules + persona (shared foundation)
    system_parts = []
    game_rules = state.get("game_rules_prompt", "")
    if game_rules:
        system_parts.append(game_rules)
    persona = state.get("persona", "")
    if persona:
        system_parts.append("你的角色人设：" + persona)
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

    # Memory context: prior thinking + public events (carries forward across rounds)
    if include_memory:
        memory = state.get("memory_context", [])
        messages.extend(memory)

    # Build user prompt with optional state appendix
    appendix_parts = []

    if include_public_state:
        public_state = state.get("public_state", {})
        if public_state:
            appendix_parts.append(
                "【当前游戏状态】\n" + json.dumps(public_state, ensure_ascii=False, indent=None)
            )

    if include_private_info:
        private_info = state.get("private_info", {})
        if private_info:
            appendix_parts.append(
                "【你的私有信息】\n" + json.dumps(private_info, ensure_ascii=False, indent=None)
            )

    # Alive player name reminder (prevents fabrication)
    alive_players = state.get("public_state", {}).get("alive_players", [])
    if alive_players:
        appendix_parts.append(
            "【存活玩家】%s（必须使用真实名字，不能用编号或编造名字）" % "、".join(alive_players)
        )

    if appendix_parts:
        user_prompt += "\n\n" + "\n\n".join(appendix_parts)

    messages.append({"role": "user", "content": user_prompt})

    return messages
