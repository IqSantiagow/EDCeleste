from textual import work
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, Vertical
from textual.widgets import Label

from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository
from edceleste.ui.screens.dashboard.widgets.stats.widget_stat_bar import WidgetStatBar

EMPTY_HOLD_PERCENT = 0.0
NO_VALUE = "-"
CLEAN_LEGAL_STATUS = "Clean"


def cargo_percent(cargo: float, cargo_capacity: float) -> float:
    if not cargo_capacity:
        return EMPTY_HOLD_PERCENT
    return cargo / cargo_capacity * 100


def credits_text(credits: float) -> str:
    return f"{credits:,.0f} CR".replace(",", " ")


class WidgetShipFlag(Label):
    DEFAULT_CLASSES = "ship-flag"

    def __init__(self, flag_name: str, **kwargs) -> None:
        super().__init__(f"○ {flag_name}", **kwargs)
        self.flag_name = flag_name

    def update_flag(self, is_flag_on: bool) -> None:
        self.update(f"{'●' if is_flag_on else '○'} {self.flag_name}")
        self.set_class(is_flag_on, "-active")


class WidgetShipStats(Vertical):
    DEFAULT_CLASSES = "stats-panel"
    BORDER_TITLE = "SHIP"

    def __init__(
        self, ed_dashboard_repository: EdDashboardRepository, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def compose(self) -> ComposeResult:
        with HorizontalGroup(classes="stat-row"):
            yield WidgetStatBar("HULL", id="hull-bar")
            yield WidgetStatBar("SHIELDS", id="shields-bar")
        with HorizontalGroup(classes="stat-row"):
            yield Label("MODULES", classes="stat-label")
            yield Label("-", classes="stat-value", id="ship-modules")
        with HorizontalGroup(classes="stat-row"):
            yield Label("PIPS", classes="stat-label")
            yield Label("SYS / ENG / WEP", classes="stat-muted")
            yield Label("0 / 0 / 0", classes="stat-value", id="ship-pips")
        with HorizontalGroup(classes="stat-row"):
            yield Label("FLAGS", classes="stat-label")
            yield WidgetShipFlag("gear", id="ship-flag-gear")
            yield WidgetShipFlag("hardpoints", id="ship-flag-hardpoints")
            yield WidgetShipFlag("lights", id="ship-flag-lights")
            yield WidgetShipFlag("shields", id="ship-flag-shields")
        with HorizontalGroup(classes="stat-row"):
            yield Label("MASS", classes="stat-label")
            yield Label("0.0 t", classes="stat-value", id="ship-mass")
            yield WidgetStatBar("CARGO", id="cargo-bar")
        with HorizontalGroup(classes="stat-row"):
            yield Label("LEGAL", classes="stat-label")
            yield Label("-", classes="stat-value", id="ship-legal")
            yield Label("REBUY", classes="stat-label")
            yield Label("0 CR", classes="stat-value", id="ship-rebuy")

    def on_mount(self) -> None:
        self.stream_ship_stats()

    @work
    async def stream_ship_stats(self) -> None:
        async for stats in self.ed_dashboard_repository.stream_ship_stats():
            self.query_one("#hull-bar", WidgetStatBar).update_bar(
                stats.hull_pe * 100, f"{stats.hull_pe * 100:.0f}%"
            )
            self.query_one("#shields-bar", WidgetStatBar).update_bar(
                stats.shields_percent, f"{stats.shields_percent:.0f}%"
            )
            self.border_subtitle = stats.ship_name
            self.query_one("#ship-modules", Label).update(
                "all nominal" if stats.modules_healthy else "damaged"
            )
            self.query_one("#ship-modules", Label).set_class(
                not stats.modules_healthy, "-alert"
            )
            pips_system, pips_engine, pips_weapons = stats.pips
            self.query_one("#ship-pips", Label).update(
                f"{pips_system} / {pips_engine} / {pips_weapons}"
            )
            self.query_one("#ship-flag-gear", WidgetShipFlag).update_flag(stats.gear)
            self.query_one("#ship-flag-hardpoints", WidgetShipFlag).update_flag(
                stats.hardpoints
            )
            self.query_one("#ship-flag-lights", WidgetShipFlag).update_flag(
                stats.lights
            )
            self.query_one("#ship-flag-shields", WidgetShipFlag).update_flag(
                stats.shields
            )
            self.query_one("#ship-mass", Label).update(f"{stats.mass:.1f} t")
            self.query_one("#cargo-bar", WidgetStatBar).update_bar(
                cargo_percent(stats.cargo, stats.cargo_capacity),
                f"{stats.cargo:.0f} / {stats.cargo_capacity:.0f} t",
            )
            self.query_one("#ship-legal", Label).update(
                stats.legal_status if stats.legal_status else NO_VALUE
            )
            self.query_one("#ship-legal", Label).set_class(
                bool(stats.legal_status) and stats.legal_status != CLEAN_LEGAL_STATUS,
                "-alert",
            )
            self.query_one("#ship-rebuy", Label).update(credits_text(stats.rebuy))
