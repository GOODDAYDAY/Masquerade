"""Game engine registry — discover and retrieve game implementations by name."""

from backend.core.exceptions import GameNotFoundError
from backend.core.logging import get_logger
from backend.engine.base import GameEngine

logger = get_logger("engine.registry")

_REGISTRY: dict[str, type[GameEngine]] = {}


def register_game(name: str):
    """Decorator to register a GameEngine subclass under a given name.

    Usage:
        @register_game("spy")
        class SpyGame(GameEngine):
            ...
    """

    def decorator(cls: type[GameEngine]) -> type[GameEngine]:
        if name in _REGISTRY:
            logger.warning("Overwriting existing game registration: %s", name)
        _REGISTRY[name] = cls
        logger.info("Registered game engine: %s -> %s", name, cls.__name__)
        return cls

    return decorator


def get_game_engine(name: str) -> type[GameEngine]:
    """Retrieve a registered game engine class by name."""
    if name not in _REGISTRY:
        raise GameNotFoundError("No game engine registered for: %s" % name)
    return _REGISTRY[name]


def list_games() -> list[str]:
    """Return all registered game names."""
    return list(_REGISTRY.keys())
