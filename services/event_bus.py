import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Awaitable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self.subscribers: dict[type, list[Callable[[Any], Awaitable[Any]]]] = (
            defaultdict(list)
        )

    def subscribe(self, event_type: type, callback: Callable[[Any], Awaitable[Any]]):
        self.subscribers[event_type].append(callback)
        logger.debug(
            "Registered new subscriber: %s with callable: %s", event_type, callback
        )

    async def publish(self, event: Any):
        logger.debug("Received app event: %s. Publishing...", event)
        for event_type, awaitables in self.subscribers.items():
            if isinstance(event, event_type):
                for awaitable in awaitables:
                    await awaitable(event)
