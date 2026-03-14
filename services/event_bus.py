import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self.subscribers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, callback: Callable):
        self.subscribers[event_type].append(callback)
        logger.debug(
            "Registered new subscriber: %s with callable: %s", event_type, callback
        )

    def publish(self, event: Any):
        logger.debug("Received app event: %s. Publishing...", event)
        for event_type, callables in self.subscribers.items():
            if isinstance(event, event_type):
                for call in callables:
                    call(event)
