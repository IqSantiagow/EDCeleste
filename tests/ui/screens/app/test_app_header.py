import asyncio
import unittest

from textual.app import App, ComposeResult
from textual.widgets import Label
from textual.worker import WorkerState

from edceleste.services.models.service_status import ServiceState, ServiceStatus
from edceleste.ui.screens.app.view_models.app_header_view_model import (
    AppHeaderViewModel,
)
from edceleste.ui.screens.app.view_models.service_statuses_view_model import (
    ServiceStatusesViewModel,
)
from edceleste.ui.screens.app.widgets.app_header import AppHeader


class FakeAppHeaderRepository:
    """Gives the header one prepared view model of service statuses and no game
    stats."""

    def __init__(self, service_statuses: ServiceStatusesViewModel):
        self.service_statuses = service_statuses

    async def stream_app_header_stats(self):
        await asyncio.Event().wait()
        yield

    async def stream_service_statuses(self):
        yield self.service_statuses
        await asyncio.Event().wait()


class QueueAppHeaderRepository:
    """Passes on service statuses and header stats only when the test puts them
    into the queues, so a test decides when the next one arrives."""

    def __init__(self):
        self.service_statuses: asyncio.Queue[ServiceStatusesViewModel] = asyncio.Queue()
        self.header_stats: asyncio.Queue[AppHeaderViewModel] = asyncio.Queue()

    async def stream_app_header_stats(self):
        while True:
            yield await self.header_stats.get()

    async def stream_service_statuses(self):
        while True:
            yield await self.service_statuses.get()


class HeaderApp(App):
    def __init__(self, repository: FakeAppHeaderRepository | QueueAppHeaderRepository):
        super().__init__()
        self.repository = repository

    def compose(self) -> ComposeResult:
        yield AppHeader(app_header_repository=self.repository)


class AppHeaderServiceDotsTest(unittest.IsolatedAsyncioTestCase):
    async def test_dots_get_symbol_colour_class_and_tooltip_from_statuses(self):
        service_statuses = ServiceStatusesViewModel(
            llm=ServiceStatus(ServiceState.OK, "The LLM answered"),
            tts=ServiceStatus(
                ServiceState.ERROR, "Celeste could not speak: no speaker"
            ),
            mic=ServiceStatus(ServiceState.OFF, "Speech-to-text is switched off"),
            journal=ServiceStatus(ServiceState.OK, "Watching the journal folder"),
        )
        app = HeaderApp(FakeAppHeaderRepository(service_statuses))

        async with app.run_test() as pilot:
            await pilot.pause(0.2)

            llm_dot = app.query_one("#stat-llm", Label)
            tts_dot = app.query_one("#stat-tts", Label)
            mic_dot = app.query_one("#stat-mic", Label)
            journal_dot = app.query_one("#stat-journal", Label)

            self.assertEqual(str(llm_dot.content), "● LLM")
            self.assertTrue(llm_dot.has_class("-ok"))
            self.assertEqual(llm_dot.tooltip, "The LLM answered")

            self.assertEqual(str(tts_dot.content), "● TTS")
            self.assertTrue(tts_dot.has_class("-error"))
            self.assertEqual(tts_dot.tooltip, "Celeste could not speak: no speaker")

            self.assertEqual(str(mic_dot.content), "○ MIC")
            self.assertTrue(mic_dot.has_class("-off"))
            self.assertEqual(mic_dot.tooltip, "Speech-to-text is switched off")

            self.assertEqual(str(journal_dot.content), "● JRNL")
            self.assertTrue(journal_dot.has_class("-ok"))
            self.assertEqual(journal_dot.tooltip, "Watching the journal folder")


class AppHeaderShutdownTest(unittest.IsolatedAsyncioTestCase):
    """On shutdown Textual removes the header children before it stops the
    header workers. remove_children() makes the same gap on purpose."""

    @staticmethod
    def find_worker(header: AppHeader, worker_name: str):
        """The running worker with this name. Take it before the status
        arrives: Textual forgets a worker as soon as it is finished."""
        return next(worker for worker in header.workers if worker.name == worker_name)

    async def test_dots_worker_ends_quietly_when_dots_are_gone(
        self,
    ):
        repository = QueueAppHeaderRepository()
        app = HeaderApp(repository)

        async with app.run_test() as pilot:
            header = app.query_one(AppHeader)
            await pilot.pause(0.2)
            worker = self.find_worker(header, "stream_service_statuses_into_dots")
            await header.remove_children()

            ok = ServiceStatus(ServiceState.OK, "fine")
            await repository.service_statuses.put(
                ServiceStatusesViewModel(llm=ok, tts=ok, mic=ok, journal=ok)
            )
            await pilot.pause(0.2)

            self.assertEqual(worker.state, WorkerState.SUCCESS)

    async def test_stats_worker_ends_quietly_when_labels_are_gone(
        self,
    ):
        repository = QueueAppHeaderRepository()
        app = HeaderApp(repository)

        async with app.run_test() as pilot:
            header = app.query_one(AppHeader)
            await pilot.pause(0.2)
            worker = self.find_worker(header, "stream_header_stats_into_state")
            await header.remove_children()

            await repository.header_stats.put(
                AppHeaderViewModel(
                    player_name="Jameson", player_ship="Cobra", credits=5
                )
            )
            await pilot.pause(0.2)

            self.assertEqual(worker.state, WorkerState.SUCCESS)


if __name__ == "__main__":
    unittest.main()
