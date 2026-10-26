import asyncio
from collections.abc import AsyncGenerator

from edceleste.services.models.service_status import ServiceState, ServiceStatus


class ServiceStatusStream:
    def __init__(self, first_status: ServiceStatus) -> None:
        """Every service keeps one of these and answers its stream_status() with
        stream_latest_status_then_every_new_one(). first_status is what a
        listener gets until the service sets a status for the first time."""
        self.latest_status = first_status
        self.queues_of_listeners: list[asyncio.Queue[ServiceStatus]] = []

    def set_status(self, state: ServiceState, reason: str) -> None:
        """Remembers the status as the latest one and puts it in the queue of
        every listener. Does not wait for anybody, raises nothing and the queues
        have no limit. The same status set twice is sent twice. reason is plain
        words for the pilot (the header shows it in a tooltip), also for OK and
        OFF. Meant for the event loop thread: SttService also calls it from the
        pynput thread, where asyncio does not promise to wake the listeners at
        once."""
        self.latest_status = ServiceStatus(state, reason)
        for queue in self.queues_of_listeners:
            queue.put_nowait(self.latest_status)

    async def stream_latest_status_then_every_new_one(
        self,
    ) -> AsyncGenerator[ServiceStatus, None]:
        """Never ends on its own. Yields the latest status right away, then
        every status set later. The caller gets its own queue, removed again
        when the caller stops iterating."""
        queue: asyncio.Queue[ServiceStatus] = asyncio.Queue()
        self.queues_of_listeners.append(queue)
        try:
            yield self.latest_status
            while True:
                yield await queue.get()
        finally:
            self.queues_of_listeners.remove(queue)
