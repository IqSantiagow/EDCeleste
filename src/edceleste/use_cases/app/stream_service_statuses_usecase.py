import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace

from edceleste.protocols.service_status_protocol import ServiceStatusProtocol
from edceleste.services.models.service_status import ServiceStatus
from edceleste.ui.screens.app.view_models.service_statuses_view_model import (
    ServiceStatusesViewModel,
)


class StreamServiceStatusesUseCase:
    def __init__(
        self,
        llm_status: ServiceStatusProtocol,
        tts_status: ServiceStatusProtocol,
        mic_status: ServiceStatusProtocol,
        journal_status: ServiceStatusProtocol,
    ) -> None:
        """Only stores the four services. They are kept in a dict under the name
        of the field of ServiceStatusesViewModel they fill, and __call__() uses
        that name to put the status of a service in the right field."""
        self.services = {
            "llm": llm_status,
            "tts": tts_status,
            "mic": mic_status,
            "journal": journal_status,
        }

    async def __call__(self) -> AsyncGenerator[ServiceStatusesViewModel, None]:
        """Never ends. Listens to stream_status() of the four services at the
        same time and yields the whole view model again (a new object, the old
        one is not changed) after every single change. Each service gives its
        latest status at once, so the first view models come right away, one
        per service; a service that has not answered yet is still OFF "Not
        checked yet". When the caller stops iterating, the four listeners are
        cancelled. An error in the stream of one service ends only the listener
        of that service: its field keeps the last status and the others go on."""
        changes: asyncio.Queue[tuple[str, ServiceStatus]] = asyncio.Queue()

        async def put_every_status_of_one_service_into_changes_queue(
            service_name: str, service: ServiceStatusProtocol
        ) -> None:
            """Runs as one task per service. Puts (service name, status) in the
            changes queue for every status the service streams."""
            async for status in service.stream_status():
                await changes.put((service_name, status))

        tasks = [
            asyncio.create_task(
                put_every_status_of_one_service_into_changes_queue(name, service)
            )
            for name, service in self.services.items()
        ]
        view_model = ServiceStatusesViewModel.empty()
        try:
            while True:
                service_name, status = await changes.get()
                view_model = replace(view_model, **{service_name: status})
                yield view_model
        finally:
            for task in tasks:
                task.cancel()
