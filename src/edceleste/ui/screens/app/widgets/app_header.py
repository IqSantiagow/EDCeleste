from dependency_injector.wiring import Provide, inject
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from datetime import datetime
from textual.reactive import reactive
from textual.widgets import Label, Rule
from textual import work
from edceleste.containers.main_container import Container
from edceleste.ui.screens.app.widgets.widget_common_stat_label import (
    WidgetCommonStatLabel,
)
from edceleste.ui.screens.app.app_header_repository import AppHeaderRepository
from edceleste.services.models.service_status import ServiceState
from edceleste.ui.screens.app.view_models.app_header_view_model import (
    AppHeaderViewModel,
)

# The field of ServiceStatusesViewModel and the text written next to its dot
SERVICE_DOT_TEXTS = {"llm": "LLM", "tts": "TTS", "mic": "MIC", "journal": "JRNL"}


class AppHeader(HorizontalGroup):
    state: reactive[AppHeaderViewModel] = reactive(AppHeaderViewModel.empty())

    time: reactive[str] = reactive("")

    @inject
    def __init__(
        self,
        app_header_repository: AppHeaderRepository = Provide[
            Container.app_header_repository
        ],
        **kwargs,
    ) -> None:
        """The repository comes from the DI container, so screens can create
        AppHeader() with no arguments. The "app-header" class is always set."""
        super().__init__(**kwargs, classes="app-header")
        self.app_header_repository = app_header_repository

    def compose(self) -> ComposeResult:
        with HorizontalGroup(id="dashboard-stats-content-left"):
            yield Label(content="EDCELESTE", id="dashboard-title")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="CMDR", stat_value="", id="stat-cmdr")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="", stat_value="", id="stat-ship")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="CR", stat_value="", id="stat-credits")
        with HorizontalGroup(id="dashboard-additional-stats-content-right"):
            yield Label("○ LLM", id="stat-llm", classes="service-dot")
            yield Label("○ TTS", id="stat-tts", classes="service-dot")
            yield Label("○ MIC", id="stat-mic", classes="service-dot")
            yield Label("○ JRNL", id="stat-journal", classes="service-dot")
            yield Label("", id="stat-time")

    def update_time(self) -> None:
        """Called every second by the timer from on_mount(). Only sets the
        time reactive, watch_time() redraws the clock."""
        self.time = datetime.now().strftime("%H:%M:%S")

    def watch_time(self, new_time: str) -> None:
        self.query_one("#stat-time", Label).content = new_time

    def on_mount(self) -> None:
        self.call_later(self.stream_header_stats_into_state)
        self.call_later(self.stream_service_statuses_into_dots)
        self.update_timer = self.set_interval(1.0, self.update_time)

    def watch_state(self, new_state: AppHeaderViewModel) -> None:
        self.query_one("#stat-cmdr", WidgetCommonStatLabel).update_value(
            new_state.player_name
        )
        self.query_one("#stat-ship", WidgetCommonStatLabel).update_value(
            new_state.player_ship
        )
        self.query_one("#stat-credits", WidgetCommonStatLabel).update_value(
            str(new_state.credits)
        )

    @work
    async def stream_service_statuses_into_dots(self) -> None:
        """Textual worker that never ends. For every new view model it draws
        the four dots: a filled dot for OK and ERROR, an empty one for OFF, the
        CSS class -ok / -off / -error gives the colour, and the reason of the
        status is the tooltip."""
        async for statuses in self.app_header_repository.stream_service_statuses():
            for service_name, dot_text in SERVICE_DOT_TEXTS.items():
                status = getattr(statuses, service_name)
                dot = self.query_one(f"#stat-{service_name}", Label)
                symbol = "○" if status.state == ServiceState.OFF else "●"
                dot.update(f"{symbol} {dot_text}")
                dot.set_classes(f"service-dot -{status.state}")
                dot.tooltip = status.reason

    @work
    async def stream_header_stats_into_state(self) -> None:
        """Textual worker that never ends. Puts every new header view model
        into the state reactive, watch_state() redraws the labels."""
        async for header_stats in self.app_header_repository.stream_app_header_stats():
            self.state = header_stats
