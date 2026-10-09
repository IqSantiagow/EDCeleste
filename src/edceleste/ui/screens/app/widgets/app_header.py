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
from edceleste.ui.screens.app.view_models.app_header_view_model import (
    AppHeaderViewModel,
)


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
        """Left: title, commander, ship and credits, all empty at first. Right:
        only the clock for now. watch_state() and watch_time() fill them in
        later."""
        with HorizontalGroup(id="dashboard-stats-content-left"):
            yield Label(content="EDCELESTE", id="dashboard-title")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="CMDR", stat_value="", id="stat-cmdr")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="", stat_value="", id="stat-ship")
            yield Rule(orientation="vertical")
            yield WidgetCommonStatLabel(text="CR", stat_value="", id="stat-credits")
            # TODO: Add right side of it
        with HorizontalGroup(id="dashboard-additional-stats-content-right"):
            #    yield WidgetCommonStatLabel(text="LLM", stat_value="", id="stat-llm")
            #    yield WidgetCommonStatLabel(text="TTS", stat_value="", id="stat-tts")
            #    yield WidgetCommonStatLabel(text="MIC", stat_value="", id="stat-mic")
            #    yield WidgetCommonStatLabel(text="JRNL", stat_value="", id="stat-jrnl")
            yield Label("", id="stat-time")

    def update_time(self) -> None:
        """Called every second by the timer from on_mount(). Only sets the
        time reactive, watch_time() redraws the clock."""
        self.time = datetime.now().strftime("%H:%M:%S")

    def watch_time(self, new_time: str) -> None:
        """Changes only the #stat-time label, the rest of the header is not
        redrawn every second."""
        self.query_one("#stat-time", Label).content = new_time

    def on_mount(self) -> None:
        """Starts two things:
        1. the stats worker (stream_header_stats_into_state), after the
           widget is fully mounted,
        2. a 1 second timer for the clock (update_time).
        """
        self.call_later(self.stream_header_stats_into_state)
        self.update_timer = self.set_interval(1.0, self.update_time)

    def watch_state(self, new_state: AppHeaderViewModel) -> None:
        """Runs every time the worker sets a new state. Copies commander, ship
        and credits into their stat labels."""
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
    async def stream_header_stats_into_state(self) -> None:
        """Textual worker that never ends. Puts every new header view model
        into the state reactive, watch_state() redraws the labels."""
        async for header_stats in self.app_header_repository.stream_app_header_stats():
            self.state = header_stats
