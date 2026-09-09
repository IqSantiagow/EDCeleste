from textual import work
from textual.screen import Screen
from typing import Literal
from textual.widgets import Label, ProgressBar, Rule, Static, Footer
from dependency_injector.wiring import inject
from textual.containers import Horizontal, HorizontalGroup, Vertical
from asyncio import sleep
from textual.reactive import reactive
from textual.content import Content


from edceleste.ui.screens.system_check.system_check_repository import (
    SystemCheckRepository,
)

EDCELESTE_BANNER = """\
█████ ████   ████ █████ █     █████  ████ █████ █████
█     █   █ █     █     █     █     █       █   █
████  █   █ █     ████  █     ████   ███    █   ████
█     █   █ █     █     █     █         █   █   █
█████ ████   ████ █████ █████ █████ ████    █   █████"""

# Marker text + CSS class for every row state, styled in ui/css.tcss
STATE_MARKERS = {
    "pending": ("[  ]", "state-pending"),
    "in_progress": ("[**]", "state-in-progress"),
    "completed": ("[ok]", "state-completed"),
    "failed": ("[!!]", "state-failed"),
}


class SystemCheckScreen(Screen[bool]):
    service_names: list[str]

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
    ]

    @inject
    def __init__(self, system_check_repository: SystemCheckRepository, **kwargs):
        self.system_check_repository = system_check_repository
        self.service_names = self.system_check_repository.get_service_names()
        super().__init__(**kwargs)

    def on_mount(self) -> None:
        self.query_one("#system-check-panel").border_title = "PREFLIGHT"
        self.start_system_check()

    def compose(self):
        with Vertical(id="system-check-panel"):
            yield Static(EDCELESTE_BANNER, id="system-check-banner")
            for service_name in self.service_names:
                yield SystemCheckRow(
                    service_name, id=f"system-check-row-{service_name}"
                )
            yield Rule(id="system-check-divider")
            with Horizontal(id="system-check-progress-row"):
                yield Label("Progress", id="system-check-progress-label")
                yield ProgressBar(id="system-check-progress", total=100, show_eta=False)
        yield Footer()

    @work
    async def start_system_check(self) -> None:
        progress_bar = self.query_one("#system-check-progress", ProgressBar)
        total_services = len(self.service_names)
        completed_services = 0
        async for (
            service_name,
            status,
        ) in self.system_check_repository.run_system_check():
            row = self.query_one(f"#system-check-row-{service_name}", SystemCheckRow)
            row.state = "in_progress"
            if status.completed and not status.message:
                row.state = "completed"
                completed_services += 1
            elif status.message:
                row.error_message = status.message
                row.state = "failed"
                if status.is_critical:
                    break
                completed_services += 1
            progress_bar.update(progress=int(completed_services / total_services * 100))

        if completed_services == total_services:
            await sleep(2)
            self.dismiss(True)


class SystemCheckRow(HorizontalGroup):
    state: reactive[Literal["pending", "in_progress", "completed", "failed"]] = (
        reactive("pending", recompose=True)
    )
    error_message: str | None = None

    def __init__(self, service_name: str, **kwargs):
        super().__init__(**kwargs)
        self.service_name = service_name

    def compose(self):
        marker, state_class = STATE_MARKERS[self.state]
        yield Label(Content(marker), classes=f"system-check-marker {state_class}")
        yield Label(
            Content(self.service_name.replace("_", " ").upper()),
            classes=f"system-check-name {state_class}",
        )
        if self.error_message:
            yield Label(
                Content(f"Error: {self.error_message}"), classes="system-check-error"
            )
