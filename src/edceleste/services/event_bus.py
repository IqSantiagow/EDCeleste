import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Awaitable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        """Starts with no subscribers. The container keeps one EventBus for the
        whole app, so every service publishes and listens on the same one."""
        self.subscribers: dict[type, list[Callable[[Any], Awaitable[Any]]]] = (
            defaultdict(list)
        )

    def subscribe(self, event_type: type, callback: Callable[[Any], Awaitable[Any]]):
        """The callback is awaited for every published event that is an
        instance of event_type, subclasses too. So a subscriber of GameEvent
        gets every game event. Nothing stops the same callback from subscribing
        twice, then it is called twice."""
        self.subscribers[event_type].append(callback)
        logger.debug(
            "Registered new subscriber: %s with callable: %s", event_type, callback
        )

    async def publish(self, event: Any):
        """Awaits every matching callback one after another, in the order they
        subscribed. It returns only when all of them are done, so a slow
        subscriber holds up the publisher.

        An error in a callback is logged and swallowed. The next callbacks still
        run and the publisher never sees the error.
        """
        logger.debug("Received app event: %s. Publishing...", event)
        for event_type, callbacks in self.subscribers.items():
            if isinstance(event, event_type):
                for callback in callbacks:
                    try:
                        await callback(event)
                    except Exception as e:
                        logger.exception(
                            "Error handling event %s with awaitable %s",
                            event,
                            callback,
                            exc_info=e,
                        )
