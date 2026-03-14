"""Simple event bus for the observer pattern."""

from collections import defaultdict
from typing import Any, Callable

from backend.core.logging import get_logger

logger = get_logger("orchestrator.event_bus")


class EventBus:
    """Publish-subscribe event bus for decoupling game components."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """Register a callback for a specific event type."""
        self._subscribers[event_type].append(callback)
        logger.debug("Subscribed to event: %s", event_type)

    def emit(self, event_type: str, data: Any = None) -> None:
        """Emit an event, notifying all subscribers."""
        callbacks = self._subscribers.get(event_type, [])
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.warning("Event handler failed for %s: %s", event_type, e)
