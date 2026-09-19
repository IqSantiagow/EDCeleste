import logging
from textual.screen import Screen
from textual.widgets import Footer, TabbedContent
from textual.containers import Grid
from textual.app import ComposeResult
from textual import on, work
from edceleste.services.models.llm_status import LLMStatus
from edceleste.ui.screens.app.widgets.app_header import AppHeader
from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_col import WidgetCommsCol
from edceleste.ui.screens.dashboard.widgets.comms.widget_comms_input import (
    WidgetCommsInput,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.ship_log_tabs import (
    ALWAYS_EXPANDED_TABS,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_panel import (
    WidgetShipLogPanel,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_extended_panel import (  # noqa: E501
    WidgetShipLogExtendedPanel,
)
from edceleste.ui.screens.dashboard.widgets.stats.widget_flight_and_drive_stats import (
    WidgetFlightAndDriveStats,
)
from edceleste.ui.screens.dashboard.widgets.stats.widget_navigation_stats import (
    WidgetNavigationStats,
)
from edceleste.ui.screens.dashboard.widgets.stats.widget_ship_stats import (
    WidgetShipStats,
)
from edceleste.ui.screens.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)

logger = logging.getLogger(__name__)


class DashboardScreen(Screen):
    BINDINGS = [
        ("ctrl+r", "app.push_settings", "Settings"),
        ("ctrl+e", "toggle_ship_log_expanded", "Expand log"),
    ]

    def __init__(
        self,
        dashboard_repository,
        settings_repository,
        game_watcher_service,
        **kwargs,
    ):
        self.dashboard_repository = dashboard_repository
        self.settings_repository = settings_repository
        self.game_watcher_service = game_watcher_service

        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self.__load_keybinds()
        self.set_up_llm_stream_worker()
        self.set_up_journal_stream_worker()

    def compose(self) -> ComposeResult:
        yield AppHeader()
        with Grid(id="app-container", classes="screen-grid"):
            yield WidgetNavigationStats(
                ed_dashboard_repository=self.dashboard_repository,
                id="navigation-stats",
            )
            yield WidgetFlightAndDriveStats(
                ed_dashboard_repository=self.dashboard_repository,
                id="flight-and-drive-stats",
            )
            yield WidgetShipStats(
                ed_dashboard_repository=self.dashboard_repository, id="ship-stats"
            )
            # Order matters: hidden children take up no grid cells, so it is
            # the order that decides what lands where in either mode.
            yield WidgetShipLogExtendedPanel(id="ship-log-wide")
            yield WidgetCommsCol(id="comms-col")
            yield WidgetShipLogPanel(id="ship-log-rail")
            yield WidgetCommsInput(
                ed_dashboard_repository=self.dashboard_repository, id="input-row"
            )
        yield Footer(id="app-footer")

    @on(WidgetCommsInput.UserCommandSubmitted)
    def handle_user_command_submitted(
        self, event: WidgetCommsInput.UserCommandSubmitted
    ) -> None:
        logger.debug("User command submitted: %s", event.command)
        self.query_one(
            "#comms-col", WidgetCommsCol
        ).response_state = CommsMessageViewModel.from_user_message(event.command)

    def __load_keybinds(self):
        # Will be as separate method, maybe in future will be used to retry
        try:
            self.settings_repository.load_keybinds()
        except FileNotFoundError as e:
            logger.warning("Could not load keybinds: %s", e)

    @on(TabbedContent.TabActivated)
    def handle_ship_log_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        tab_id = event.pane.id
        if not tab_id:
            return

        for tabs in self.query(TabbedContent):
            if tabs.active != tab_id:
                tabs.active = tab_id

        # Order matters: line the tabs up first, or the wide panel shows up
        # still on the previous card and flashes its contents.
        self.query_one("#app-container", Grid).set_class(
            tab_id in ALWAYS_EXPANDED_TABS, "-ship-log-expanded"
        )

    def action_toggle_ship_log_expanded(self) -> None:
        """Switch the journal between the rail and full width.

        Which panel is visible and how the grid is laid out both follow from
        this single class - ui/css.tcss does the rest. Cards listed in
        ALWAYS_EXPANDED_TABS have no rail version, so while one of them is
        open there is nothing to shrink down to.
        """
        if self.active_ship_log_tab() in ALWAYS_EXPANDED_TABS:
            return
        self.query_one("#app-container", Grid).toggle_class("-ship-log-expanded")

    def active_ship_log_tab(self) -> str:
        return self.query_one("#ship-log-wide TabbedContent", TabbedContent).active

    @work
    async def set_up_journal_stream_worker(self) -> None:
        """The only consumer of the journal stream - feeds both log panels."""
        async for entry in self.dashboard_repository.stream_journal_events():
            self.query_one("#ship-log-rail", WidgetShipLogPanel).add_entry(entry)
            self.query_one("#ship-log-wide", WidgetShipLogExtendedPanel).add_entry(
                entry
            )

    @work
    async def set_up_llm_stream_worker(self) -> None:
        """The only consumer of the LLM queue - status to input, entries to COMMS."""
        logger.debug("Starting to stream LLM items")
        async for item in self.dashboard_repository.stream_llm_responses():
            if isinstance(item, LLMStatus):
                self.query_one("#input-row", WidgetCommsInput).llm_state = item
            else:
                self.query_one("#comms-col", WidgetCommsCol).response_state = item

    def on_unmount(self) -> None:
        self.game_watcher_service.stop_watcher_service()
