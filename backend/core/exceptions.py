"""Custom exception hierarchy for the Masquerade platform."""


class MasqueradeError(Exception):
    """Base exception for all Masquerade errors."""


class IllegalActionError(MasqueradeError):
    """Raised when an invalid game action is attempted."""


class GameNotFoundError(MasqueradeError):
    """Raised when a requested game type is not registered."""


class LLMClientError(MasqueradeError):
    """Raised when an LLM API call fails after retries."""


class ConfigError(MasqueradeError):
    """Raised when configuration loading or validation fails."""
