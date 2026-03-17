"""Shared context builder for all agent decision nodes.

Ensures thinker, evaluator, and optimizer all receive consistent game context.
Each node calls build_node_messages() instead of manually assembling LLM messages.
"""

import json

from backend.agent.state import AgentState


def build_node_messages(
    state: AgentState,
    user_prompt: str,
    *,
    include_memory: bool = True,
    include_public_state: bool = True,
    include_private_info: bool = True,
) -> list[dict]:
    """Build LLM messages with full game context.

    Structure (mirrors thinker's proven pattern):
      1. System message: game_rules + persona
      2. Memory context messages (if include_memory)
      3. User message: node-specific prompt + game state appendix

    Args:
        state: Full agent state from the LangGraph workflow.
        user_prompt: The node-specific prompt (thinker/evaluator/optimizer template).
        include_memory: Inject prior thinking and public events as context messages.
        include_public_state: Append public_state JSON to user prompt.
        include_private_info: Append private_info JSON to user prompt.

    Returns:
        List of chat messages ready for LLM call.
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
