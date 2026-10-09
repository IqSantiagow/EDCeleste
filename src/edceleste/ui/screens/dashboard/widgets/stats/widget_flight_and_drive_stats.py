from textual import work
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, Vertical
from textual.widgets import Digits, Label

from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository
from edceleste.ui.screens.dashboard.widgets.stats.widget_stat_bar import WidgetStatBar

EMPTY_TANK_PERCENT = 0.0

FSD_RATINGS = {"5": "A", "4": "B", "3": "C", "2": "D", "1": "E"}


def fuel_percent(fuel: float, fuel_capacity: float) -> float:
    """0-100 for the tank bar. An unknown tank size (0) gives an empty bar
    instead of a division by zero."""
    if not fuel_capacity:
        return EMPTY_TANK_PERCENT
    return fuel / fuel_capacity * 100


def fsd_module_text(fsd_module_item: str) -> str:
    """Turns the journal item name into the in-game short name:
    "int_hyperdrive_size5_class5" -> "FSD 5A". Class 5 is A, class 1 is E.
    A name without the "size<n>_class<n>" ending is returned as it is."""
    name_parts = fsd_module_item.split("_")
    if len(name_parts) < 2 or not name_parts[-2].startswith("size"):
        return fsd_module_item

    size = name_parts[-2].removeprefix("size")
    rating = FSD_RATINGS.get(name_parts[-1].removeprefix("class"), "")
    return f"FSD {size}{rating}"


def scoop_text(is_scooping: bool) -> str:
    """Filled dot while the fuel scoop is working, empty dot otherwise."""
    return "● ACTIVE" if is_scooping else "○ IDLE"


class WidgetFlightAndDriveStats(Vertical):
    DEFAULT_CLASSES = "stats-panel"
    BORDER_TITLE = "FLIGHT & DRIVE"

    def __init__(
        self, ed_dashboard_repository: EdDashboardRepository, **kwargs
    ) -> None:
        """Only stores the repository. The stats start streaming in
        on_mount()."""
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def compose(self) -> ComposeResult:
        """Fuel and jump range as big digits, the tank bar, the scoop badge and
        the reservoir. Everything starts at zero / IDLE until the first stats
        arrive."""
        with HorizontalGroup(classes="stat-digits-row"):
            with Vertical():
                yield Label("FUEL MAIN", classes="stat-label")
                yield Digits(value="0.0", id="fuel-main-digits")
            with Vertical():
                yield Label("JUMP RANGE", classes="stat-label")
                yield Digits(value="0.0", id="jump-range-digits")
        yield WidgetStatBar("TANK", id="fuel-bar")
        with HorizontalGroup(classes="stat-row"):
            yield Label("SCOOP", classes="stat-label")
            yield Label(scoop_text(False), classes="stat-badge", id="scoop-state")
            yield Label("RESERVOIR", classes="stat-label")
            yield Label("0.0 T", classes="stat-value", id="fuel-reservoir")

    def on_mount(self) -> None:
        """Starts the worker that keeps this panel up to date."""
        self.stream_flight_and_drive_stats()

    @work
    async def stream_flight_and_drive_stats(self) -> None:
        """Textual worker that runs as long as the widget lives. For every new
        stats from the repository it rewrites the whole panel: FSD name in the
        border subtitle, fuel, jump range, tank bar, scoop badge (highlighted
        while scooping) and reservoir."""
        async for stats in self.ed_dashboard_repository.stream_flight_and_drive_stats():
            percent_of_tank = fuel_percent(stats.fuel, stats.fuel_capacity)
            self.border_subtitle = fsd_module_text(stats.fsd_module)
            self.query_one("#fuel-main-digits", Digits).update(f"{stats.fuel:.1f}")
            self.query_one("#jump-range-digits", Digits).update(
                f"{stats.jump_range:.1f}"
            )
            self.query_one("#fuel-bar", WidgetStatBar).update_bar(
                percent_of_tank,
                f"{percent_of_tank:.0f}% of {stats.fuel_capacity:.1f} T",
            )
            self.query_one("#scoop-state", Label).update(scoop_text(stats.is_scooping))
            self.query_one("#scoop-state", Label).set_class(
                stats.is_scooping, "-active"
            )
            self.query_one("#fuel-reservoir", Label).update(
                f"{stats.fuel_reservoir:.2f} T"
            )
