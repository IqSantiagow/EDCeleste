from textual import work
from textual.app import ComposeResult
from textual.containers import HorizontalGroup, Vertical
from textual.widgets import Label, Rule

from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository

NO_VALUE = "-"


def value_or_dash(value: str) -> str:
    return value if value else NO_VALUE


def security_badge_text(security: str) -> str:
    if not security:
        return ""
    return f"● {security.upper()}"


def economy_text(economy: str, second_economy: str) -> str:
    known_economies = [name for name in (economy, second_economy) if name]
    if not known_economies:
        return NO_VALUE
    return " / ".join(known_economies)


def population_text(population: int) -> str:
    if not population:
        return NO_VALUE
    return f"{population:,}".replace(",", " ")


def jumps_left_text(remaining_jumps: int) -> str:
    if not remaining_jumps:
        return ""
    return f"{remaining_jumps} jumps left"


class WidgetNavigationStats(Vertical):
    DEFAULT_CLASSES = "stats-panel"
    BORDER_TITLE = "NAVIGATION"

    def __init__(
        self, ed_dashboard_repository: EdDashboardRepository, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def compose(self) -> ComposeResult:
        with HorizontalGroup(classes="stat-row"):
            yield Label("SYSTEM", classes="stat-label")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-system")
            yield Label("", classes="stat-badge", id="navigation-security")
        with HorizontalGroup(classes="stat-row"):
            yield Label("BODY", classes="stat-label")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-body")
        with HorizontalGroup(classes="stat-row"):
            yield Label("STATUS", classes="stat-label")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-status")
        yield Rule(classes="section-divider")
        with HorizontalGroup(classes="stat-row"):
            yield Label("NEXT", classes="stat-label")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-route-next")
            yield Label("", classes="stat-muted", id="navigation-route-jumps")
        with HorizontalGroup(classes="stat-row"):
            yield Label("ALLEGIANCE", classes="stat-label")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-allegiance")
            yield Label("GOV", classes="stat-label inline")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-government")
        with HorizontalGroup(classes="stat-row"):
            yield Label("ECONOMY", classes="stat-label")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-economy")
        with HorizontalGroup(classes="stat-row"):
            yield Label("POPULATION", classes="stat-label")
            yield Label(NO_VALUE, classes="stat-value", id="navigation-population")

    def on_mount(self) -> None:
        self.stream_navigation_stats()

    @work
    async def stream_navigation_stats(self) -> None:
        async for stats in self.ed_dashboard_repository.stream_navigation_stats():
            self.query_one("#navigation-system", Label).update(
                value_or_dash(stats.system)
            )
            self.query_one("#navigation-security", Label).update(
                security_badge_text(stats.security)
            )
            self.query_one("#navigation-body", Label).update(value_or_dash(stats.body))
            self.query_one("#navigation-status", Label).update(stats.status.upper())
            self.query_one("#navigation-route-next", Label).update(
                value_or_dash(stats.route_next_system)
            )
            self.query_one("#navigation-route-jumps", Label).update(
                jumps_left_text(stats.route_remaining_jumps)
            )
            self.query_one("#navigation-allegiance", Label).update(
                value_or_dash(stats.allegiance)
            )
            self.query_one("#navigation-government", Label).update(
                value_or_dash(stats.government)
            )
            self.query_one("#navigation-economy", Label).update(
                economy_text(stats.economy, stats.second_economy)
            )
            self.query_one("#navigation-population", Label).update(
                population_text(stats.population)
            )
