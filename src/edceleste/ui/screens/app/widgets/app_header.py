from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.reactive import reactive
from textual.widgets import Label, Rule
from textual import work
from edceleste.ui.screens.app.widgets.widget_common_stat_label import (
    WidgetCommonStatLabel,
)
from edceleste.ui.screens.app.app_header_repository import AppHeaderRepository
from edceleste.ui.screens.app.view_models.app_header_view_model import (
    AppHeaderViewModel,
)


class AppHeader(HorizontalGroup):
    state: reactive[AppHeaderViewModel] = reactive(AppHeaderViewModel.empty())

    def __init__(self, app_header_repository: AppHeaderRepository, **kwargs) -> None:
        super().__init__(id="app-header", **kwargs)
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
            # TODO: Add right side of it
        # with HorizontalGroup(id="dashboard-additional-stats-content-right"):
        #     yield WidgetCommonStatLabel(text="LLM", stat_value="", id="stat-llm")
        #     yield WidgetCommonStatLabel(text="TTS", stat_value="", id="stat-tts")
        #     yield WidgetCommonStatLabel(text="MIC", stat_value="", id="stat-mic")
        #     yield WidgetCommonStatLabel(text="JRNL", stat_value="", id="stat-jrnl")

    def on_mount(self) -> None:
        self.call_later(self.set_up_stream_worker)

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
    async def set_up_stream_worker(self) -> None:
        async for (
            dashboard_state
        ) in self.app_header_repository.stream_app_header_stats():
            self.state = dashboard_state
