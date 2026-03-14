"""Player memory management — isolates private and public knowledge."""


class PlayerMemory:
    """Maintains separated private (thinking) and public (observable) memory for a player."""

    def __init__(self) -> None:
        self.private_memory: list[str] = []
        self.public_memory: list[str] = []

    def add_private(self, content: str) -> None:
        """Record a private thought (only visible to this player)."""
        self.private_memory.append(content)

    def add_public(self, content: str) -> None:
        """Record a public event (visible to all players)."""
        self.public_memory.append(content)

    def build_context_messages(self) -> list[dict]:
        """Build chat messages from memory for LLM context injection."""
        messages: list[dict] = []

        if self.public_memory:
            public_text = "\n".join(self.public_memory)
            messages.append({
                "role": "user",
                "content": "以下是目前为止的公开信息：\n" + public_text,
            })

        if self.private_memory:
            private_text = "\n".join(self.private_memory)
            messages.append({
                "role": "assistant",
                "content": "我之前的思考：\n" + private_text,
            })

        return messages
