from dataclasses import dataclass

from textual import on, work
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.content import Content
from textual.widgets import Button, Label, ProgressBar

from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctModelState,
    InstinctStatus,
    describe_download_progress,
    describe_size,
)
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.widgets.common.widget_spinner import WidgetSpinner

SECONDS_BETWEEN_REDRAWS = 0.1
BUSY_STATES = (InstinctModelState.DOWNLOADING, InstinctModelState.LOADING)


@dataclass
class StatusLine:
    text: str
    css_class: str
    button_name: str | None


class WidgetInstinctStatusRow(HorizontalGroup):
    DEFAULT_CLASSES = "entry-row-full"

    def __init__(self, settings_repository: SettingsRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings_repository = settings_repository
        self.download_size: int | None = None

    def compose(self) -> ComposeResult:
        yield Label("Status:", classes="entry-label")
        with HorizontalGroup(id="instinct-status-content"):
            yield WidgetSpinner(id="instinct-status-spinner")
            yield Label("", id="instinct-status-text")
            yield ProgressBar(
                id="instinct-download-bar", show_eta=False, show_percentage=False
            )
            yield Label("", id="instinct-download-figures")
        yield WidgetButton("Download", id="instinct-status-button")

    def on_mount(self) -> None:
        self.show_status()
        # the download runs in the Instinct service, the row only draws it,
        # so it keeps going when the pilot leaves the settings
        self.set_interval(SECONDS_BETWEEN_REDRAWS, self.show_status)
        self.fetch_download_size()

    @work
    async def fetch_download_size(self) -> None:
        self.download_size = await self.settings_repository.get_instinct_download_size()

    def show_status(self) -> None:
        status = self.settings_repository.get_instinct_status()
        self.show_spinner(status.state in BUSY_STATES)
        self.show_download_progress(
            status.download_progress
            if status.state == InstinctModelState.DOWNLOADING
            else None
        )

        status_line = self.build_status_line(status)
        status_label = self.query_one("#instinct-status-text", Label)
        status_label.update(Content(status_line.text))
        status_label.set_classes(status_line.css_class)
        button = self.query_one("#instinct-status-button", WidgetButton)
        button.display = status_line.button_name is not None
        button.label = Content(f"[{status_line.button_name}]")

    def show_spinner(self, is_busy: bool) -> None:
        spinner = self.query_one("#instinct-status-spinner", WidgetSpinner)
        spinner.display = is_busy
        if is_busy:
            spinner.start()
        else:
            spinner.stop()

    def show_download_progress(self, progress: DownloadProgress | None) -> None:
        progress_bar = self.query_one("#instinct-download-bar", ProgressBar)
        figures_label = self.query_one("#instinct-download-figures", Label)
        progress_bar.display = progress is not None
        figures_label.display = progress is not None
        if progress:
            progress_bar.update(
                total=progress.bytes_total, progress=progress.bytes_done
            )
            figures_label.update(describe_download_progress(progress))

    def build_status_line(self, status: InstinctStatus) -> StatusLine:
        match status.state:
            case InstinctModelState.DOWNLOADING:
                return StatusLine("Downloading", "busy", "Cancel")
            case InstinctModelState.LOADING:
                return StatusLine("Loading the model", "busy", None)
            case InstinctModelState.READY if status.running_device:
                return StatusLine(
                    f"✓ Ready · running on {status.running_device}", "ready", None
                )
            case InstinctModelState.READY:
                return StatusLine("✓ Ready", "ready", None)
            case InstinctModelState.FAILED if status.failure:
                failed_step = status.failure.step.capitalize()
                reason = status.failure.reason
                return StatusLine(
                    f"✗ {failed_step} failed: {reason}", "failed", "Retry"
                )
            case _:
                if self.download_size is None:
                    return StatusLine("○ Not downloaded", "", "Download")
                size = describe_size(self.download_size)
                return StatusLine(f"○ Not downloaded · {size}", "", "Download")

    @on(Button.Pressed, "#instinct-status-button")
    def handle_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        # [Download], [Cancel] and [Retry] act on the fixed model, not on the
        # values on screen, so they never mark the settings as modified
        state = self.settings_repository.get_instinct_status().state
        if state == InstinctModelState.DOWNLOADING:
            self.settings_repository.cancel_instinct_download()
        else:
            self.settings_repository.download_instinct_model()
        self.show_status()
