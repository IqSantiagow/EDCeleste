import asyncio
import unittest

from edceleste.services.models.service_status import ServiceState, ServiceStatus
from edceleste.services.service_status_stream import ServiceStatusStream
from edceleste.use_cases.app.stream_service_statuses_usecase import (
    StreamServiceStatusesUseCase,
)
from edceleste.ui.screens.app.view_models.service_statuses_view_model import (
    ServiceStatusesViewModel,
)


class FakeService:
    """A service with only the stream_status method of ServiceStatusProtocol."""

    def __init__(self, reason: str):
        self.status_stream = ServiceStatusStream(ServiceStatus(ServiceState.OK, reason))

    def stream_status(self):
        return self.status_stream.stream_latest_status_then_every_new_one()


async def _read_until(stream, condition) -> ServiceStatusesViewModel:
    """Reads view models from the stream until one fits the condition. Fails
    after one second, so a test waiting for a view model that never comes does
    not hang."""

    async def read():
        async for view_model in stream:
            if condition(view_model):
                return view_model

    return await asyncio.wait_for(read(), timeout=1)


def _has_every_first_status(view_model: ServiceStatusesViewModel) -> bool:
    return (
        view_model.llm.reason == "llm reason"
        and view_model.tts.reason == "tts reason"
        and view_model.mic.reason == "mic reason"
        and view_model.journal.reason == "journal reason"
    )


class StreamServiceStatusesUseCaseTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.llm = FakeService("llm reason")
        self.tts = FakeService("tts reason")
        self.mic = FakeService("mic reason")
        self.journal = FakeService("journal reason")
        self.use_case = StreamServiceStatusesUseCase(
            llm_status=self.llm,
            tts_status=self.tts,
            mic_status=self.mic,
            journal_status=self.journal,
        )

    async def test_every_service_status_lands_in_its_own_field(self):
        stream = self.use_case()
        self.addAsyncCleanup(stream.aclose)

        view_model = await _read_until(stream, _has_every_first_status)

        self.assertEqual(view_model.llm, ServiceStatus(ServiceState.OK, "llm reason"))
        self.assertEqual(view_model.tts, ServiceStatus(ServiceState.OK, "tts reason"))
        self.assertEqual(view_model.mic, ServiceStatus(ServiceState.OK, "mic reason"))
        self.assertEqual(
            view_model.journal, ServiceStatus(ServiceState.OK, "journal reason")
        )

    async def test_a_change_of_one_service_leaves_the_others_untouched(self):
        stream = self.use_case()
        self.addAsyncCleanup(stream.aclose)
        await _read_until(stream, _has_every_first_status)

        self.mic.status_stream.set_status(ServiceState.ERROR, "unplugged")
        view_model = await _read_until(
            stream, lambda view_model: view_model.mic.state == ServiceState.ERROR
        )

        self.assertEqual(view_model.mic, ServiceStatus(ServiceState.ERROR, "unplugged"))
        self.assertEqual(view_model.llm.reason, "llm reason")
        self.assertEqual(view_model.tts.reason, "tts reason")
        self.assertEqual(view_model.journal.reason, "journal reason")

    async def test_two_streams_at_once_both_get_every_change(self):
        first_stream = self.use_case()
        second_stream = self.use_case()
        self.addAsyncCleanup(first_stream.aclose)
        self.addAsyncCleanup(second_stream.aclose)
        await _read_until(first_stream, _has_every_first_status)
        await _read_until(second_stream, _has_every_first_status)

        self.llm.status_stream.set_status(ServiceState.ERROR, "bad key")

        def llm_failed(view_model):
            return view_model.llm.state == ServiceState.ERROR

        first_view_model = await _read_until(first_stream, llm_failed)
        second_view_model = await _read_until(second_stream, llm_failed)
        self.assertEqual(first_view_model.llm.reason, "bad key")
        self.assertEqual(second_view_model.llm.reason, "bad key")

    async def test_the_four_listeners_are_cancelled_when_the_caller_stops(self):
        stream = self.use_case()
        await _read_until(stream, _has_every_first_status)

        await stream.aclose()
        for _ in range(5):
            await asyncio.sleep(0)

        for service in (self.llm, self.tts, self.mic, self.journal):
            self.assertEqual(service.status_stream.queues_of_listeners, [])


if __name__ == "__main__":
    unittest.main()
