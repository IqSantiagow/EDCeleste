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
        """Only keeps the dependencies. UIApp passes them in, they are not
        injected. game_watcher_service is kept only to stop it on unmount."""
        self.dashboard_repository = dashboard_repository
        self.settings_repository = settings_repository
        self.game_watcher_service = game_watcher_service

        super().__init__(**kwargs)

    def on_mount(self) -> None:
        """1. Loads the keybinds. A missing keybinds file only logs a warning.
        2. Starts the LLM worker (show_llm_replies_and_status).
        3. Starts the journal worker (show_journal_entries_in_ship_log).
        """
        self.__load_keybinds()
        self.show_llm_replies_and_status()
        self.show_journal_entries_in_ship_log()

    def compose(self) -> ComposeResult:
        """Header on top, footer at the bottom, and in between one grid with
        the three stats panels, both ship log panels (wide and rail), COMMS
        and the input row. The stats panels and the input get the repository,
        the log panels and COMMS are fed by this screen's workers."""
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
        """WidgetCommsInput posts it when the pilot sends a command. Shows the
        command in COMMS as the pilot's line. Sending it to the LLM is done by
        the input widget, not here."""
        logger.debug("User command submitted: %s", event.command)
        self.query_one(
            "#comms-col", WidgetCommsCol
        ).response_state = CommsMessageViewModel.from_user_message(event.command)

    def __load_keybinds(self):
        """A missing keybinds file is not fatal: it logs a warning and the
        dashboard opens anyway. Other errors are not caught."""
        # Will be as separate method, maybe in future will be used to retry
        try:
            self.settings_repository.load_keybinds()
        except FileNotFoundError as e:
            logger.warning("Could not load keybinds: %s", e)

    @on(TabbedContent.TabActivated)
    def handle_ship_log_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Runs when a tab is picked in either ship log panel.

        1. A tab with no id is ignored.
        2. Switches every TabbedContent on the screen to the same tab, so the
           wide and the rail panel always show the same card.
        3. Sets the "-ship-log-expanded" class on the grid when the card is in
           ALWAYS_EXPANDED_TABS, and removes it otherwise.
        """
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
        """Id of the open card, read from the wide panel. Both panels always
        show the same card (see handle_ship_log_tab_activated)."""
        return self.query_one("#ship-log-wide TabbedContent", TabbedContent).active

    @work
    async def show_journal_entries_in_ship_log(self) -> None:
        """The only consumer of the journal stream - feeds both log panels.

        Textual worker that never ends. Every journal entry is added to the
        rail panel and to the wide panel, so the hidden one is always up to
        date when the pilot toggles the layout."""
        async for entry in self.dashboard_repository.stream_journal_events():
            self.query_one("#ship-log-rail", WidgetShipLogPanel).add_entry(entry)
            self.query_one("#ship-log-wide", WidgetShipLogExtendedPanel).add_entry(
                entry
            )

    @work
    async def show_llm_replies_and_status(self) -> None:
        """The only consumer of the LLM queue - status to input, entries to COMMS.

        Textual worker that never ends. An LLMStatus (thinking / idle) goes to
        the input row, every other item is a COMMS message and goes to COMMS.
        Messages typed by the pilot and replies to journal events both come
        through here."""
        logger.debug("Starting to stream LLM items")
        async for item in self.dashboard_repository.stream_llm_responses():
            if isinstance(item, LLMStatus):
                self.query_one("#input-row", WidgetCommsInput).llm_state = item
            else:
                self.query_one("#comms-col", WidgetCommsCol).response_state = item

    def on_unmount(self) -> None:
        """Stops the game watcher (journal and status file polling) when the
        dashboard goes away, so no tasks keep running after the app closes."""
        self.game_watcher_service.stop_watcher_service()
