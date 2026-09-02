import asyncio
from dataclasses import dataclass

from dependency_injector.wiring import inject, Provide
from textual import on, work
from textual.content import Content
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Label, Static, Button, Input, Sparkline, Switch
from textual.containers import Vertical, VerticalScroll, Horizontal, Center
from textual_fspicker import FileOpen, Filters
from pathlib import Path

from edceleste.containers.main_container import Container
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    DEFAULT_VOICE_SAMPLE_TEXT,
    VoiceAnalysisResult,
)
from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader
from edceleste.ui.widgets.common.widget_spinner import WidgetSpinner


@dataclass(frozen=True)
class VoiceCloneSaveResult:
    profile_name: str
    set_as_active: bool


# The 4 real steps clone_voice() reports (VoiceCloningState, in yield order).
# Labels describe what just finished, not marketing fluff - keep them tied to
# what the provider actually does.
CLONING_STEP_LABELS = [
    "Preparing profile",
    "Loading sample",
    "Extracting voice features (Chatterbox)",
    "Saving profile and demo sample",
]


def format_seconds_as_clock(seconds: float) -> str:
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes:02d}:{remaining_seconds:04.1f}"


class AnalysisCheckRow(Horizontal):
    DEFAULT_CLASSES = "analysis-check-row"

    def __init__(self, label: str, value: str, is_ok: bool, hint: str = "", **kwargs):
        super().__init__(**kwargs)
        self.check_label = label
        self.check_value = value
        self.is_ok = is_ok
        self.check_hint = hint

    def compose(self):
        icon = "✓" if self.is_ok else "✗"
        icon_status_class = "success" if self.is_ok else "error"
        yield Label(
            icon, classes=f"analysis-check-icon warning-label {icon_status_class}"
        )
        yield Label(self.check_label, classes="analysis-check-label")
        yield Label(self.check_value, classes="analysis-check-value")
        yield Label(self.check_hint, classes="analysis-check-hint")


class AnalysisPhase(Static):
    class AnalysisCompleted(Message):
        def __init__(self, is_valid: bool) -> None:
            super().__init__()
            self.is_valid = is_valid

    def __init__(self, file_path: Path, settings_repository: SettingsRepository):
        self.file_path = file_path
        self.settings_repository = settings_repository
        self.analysis: VoiceAnalysisResult | None = None
        super().__init__()

    def on_mount(self):
        self.run_analysis()

    @work
    async def run_analysis(self) -> None:
        self.analysis = await asyncio.to_thread(
            self.settings_repository.analyze_voice_sample, str(self.file_path)
        )
        self.post_message(self.AnalysisCompleted(self.analysis["is_valid"]))
        await self.recompose()

    def compose(self):
        with Vertical(classes="voice-clone-body analysis-phase-body"):
            if self.analysis is None:
                yield Label("Analyzing sample...", classes="analysis-status-label")
                return

            yield Label("Selected file", classes="analysis-heading")
            yield Label(self.analysis["file_name"], classes="analysis-file-name")
            yield Label(str(self.file_path.parent), classes="analysis-file-dir")

            yield Sparkline(self.analysis["waveform_envelope"], id="analysis-waveform")
            with Horizontal(classes="analysis-waveform-time-row"):
                yield Label("00:00", classes="analysis-waveform-time-start")
                yield Label(
                    format_seconds_as_clock(self.analysis["duration_seconds"]),
                    classes="analysis-waveform-time-end",
                )

            yield from self._compose_check_rows()

            with Center():
                yield WidgetButton("▶ Play", id="analysis-play-button")

            if not self.analysis["is_valid"]:
                yield Label(
                    "Chatterbox needs a longer sample to capture the voice's timbre.",
                    classes="analysis-error-hint",
                )

    def _compose_check_rows(self):
        analysis = self.analysis
        assert analysis is not None

        yield AnalysisCheckRow(
            "Duration",
            f"{analysis['duration_seconds']:.1f}s",
            is_ok=analysis["is_valid"],
            hint=analysis["validation_error_message"] or "(recommended 10-30s)",
        )
        yield AnalysisCheckRow(
            "Channels",
            "mono" if analysis["is_mono"] else "stereo",
            is_ok=True,
        )
        yield AnalysisCheckRow(
            "Sample rate", f"{analysis['sample_rate']} Hz", is_ok=True
        )
        yield AnalysisCheckRow(
            "Peak",
            f"{analysis['peak_dbfs']:.1f} dBFS",
            is_ok=True,
            hint="(clipping!)" if analysis["has_clipping"] else "(no clipping)",
        )
        yield AnalysisCheckRow(
            "Noise floor", f"{analysis['noise_floor_dbfs']:.0f} dB", is_ok=True
        )

    @on(Button.Pressed, "#analysis-play-button")
    def handle_play_pressed(self) -> None:
        self.play_sample()

    @work
    async def play_sample(self) -> None:
        await self.settings_repository.play_audio_file(str(self.file_path))


class CloningStepRow(Horizontal):
    """One line in the cloning checklist: ○ pending -> spinner active -> ✓/✗ done."""

    DEFAULT_CLASSES = "analysis-check-row"

    def __init__(self, label: str, **kwargs):
        super().__init__(**kwargs)
        self.step_label = label

    def compose(self):
        yield Label("○", classes="analysis-check-icon warning-label", id="step-icon")
        yield WidgetSpinner(classes="analysis-check-icon hidden", id="step-spinner")
        yield Label(self.step_label, classes="analysis-check-label")

    def mark_active(self) -> None:
        self.query_one("#step-icon", Label).add_class("hidden")
        spinner = self.query_one("#step-spinner", WidgetSpinner)
        spinner.remove_class("hidden")
        spinner.start()

    def mark_done(self) -> None:
        self._show_icon("✓", "success")

    def mark_failed(self) -> None:
        self._show_icon("✗", "error")

    def _show_icon(self, icon: str, status_class: str) -> None:
        spinner = self.query_one("#step-spinner", WidgetSpinner)
        spinner.stop()
        spinner.add_class("hidden")
        step_icon = self.query_one("#step-icon", Label)
        step_icon.update(icon)
        step_icon.set_classes(f"analysis-check-icon warning-label {status_class}")


class SavePhase(Static):
    class CloningCompleted(Message):
        def __init__(self, is_successful: bool) -> None:
            super().__init__()
            self.is_successful = is_successful

    # Flips from the cloning checklist to the "name it and try it" view once
    # clone_voice() finishes - recompose=True redraws compose() on flip.
    is_ready: reactive[bool] = reactive(False, recompose=True)

    def __init__(self, file_path: Path, settings_repository: SettingsRepository):
        self.file_path = file_path
        # The name the profile already lives under on disk since clone_voice()
        # ran. The user can rename it before saving - see attempt_save().
        self.temporary_profile_name = file_path.stem
        self.settings_repository = settings_repository
        super().__init__()

    def on_mount(self):
        self.run_clone_voice()

    def compose(self):
        with VerticalScroll(
            classes="voice-clone-body analysis-phase-body", id="save-phase-body"
        ):
            if not self.is_ready:
                yield Label(
                    f"{self.file_path.name} → {self.temporary_profile_name}",
                    classes="analysis-heading",
                )
                for step_label in CLONING_STEP_LABELS:
                    yield CloningStepRow(step_label)
                return

            yield from self._compose_ready_view()

    def _compose_ready_view(self):
        yield Label("✓ Profile ready", classes="warning-label success")

        yield Label("Profile name", classes="analysis-heading")
        yield Input(
            self.temporary_profile_name,
            id="save-profile-name-input",
            compact=True,
        )
        yield Label("name must be unique", classes="analysis-check-hint")
        yield Label("", id="save-name-error", classes="analysis-error-hint hidden")

        with Horizontal(classes="save-toggle-row"):
            yield Label("Set as active", classes="analysis-heading")
            yield Switch(value=True, id="save-active-toggle")

        yield WidgetSectionHeader("COMPARE")

        with Horizontal(classes="analysis-check-row"):
            yield Label("A source file", classes="analysis-heading")
            yield WidgetButton("▶", id="compare-play-source-button")
        with Horizontal(classes="analysis-check-row"):
            yield Label("B clone synthesis", classes="analysis-heading")
            yield WidgetButton("▶", id="compare-play-sample-button")

        yield Label("Sample text:", classes="analysis-heading")
        yield Input(
            DEFAULT_VOICE_SAMPLE_TEXT,
            id="save-sample-text-input",
            compact=True,
        )
        with Horizontal(classes="save-toggle-row"):
            yield Label(
                "(you can change it and resynthesize)", classes="analysis-check-hint"
            )
            yield WidgetButton("↻ Regenerate", id="save-regenerate-button")

    @work
    async def run_clone_voice(self) -> None:
        steps = list(self.query(CloningStepRow))
        step_index = 0
        steps[step_index].mark_active()

        try:
            async for _cloning_state in self.settings_repository.clone_voice(
                str(self.file_path), self.temporary_profile_name
            ):
                steps[step_index].mark_done()
                step_index += 1
                if step_index < len(steps):
                    steps[step_index].mark_active()
        except Exception as e:
            if step_index < len(steps):
                steps[step_index].mark_failed()
            self.query_one("#save-phase-body").mount(
                Label(
                    f"Cloning failed: {e}",
                    classes="analysis-error-hint",
                )
            )
            self.post_message(self.CloningCompleted(is_successful=False))
            return

        self.is_ready = True
        self.post_message(self.CloningCompleted(is_successful=True))

    @on(Button.Pressed, "#compare-play-source-button")
    def handle_play_source_pressed(self) -> None:
        self.play_source()

    @on(Button.Pressed, "#compare-play-sample-button")
    def handle_play_sample_pressed(self) -> None:
        self.play_sample()

    @work(exclusive=True, group="ab-playback")
    async def play_source(self) -> None:
        await self.settings_repository.play_audio_file(str(self.file_path))

    @work(exclusive=True, group="ab-playback")
    async def play_sample(self) -> None:
        await self.settings_repository.play_sample_voice(self.temporary_profile_name)

    @on(Button.Pressed, "#save-regenerate-button")
    def handle_regenerate_pressed(self) -> None:
        self.preview_sample_with_custom_text()

    @work(exclusive=True, group="ab-playback")
    async def preview_sample_with_custom_text(self) -> None:
        new_text = self.query_one("#save-sample-text-input", Input).value
        await self.settings_repository.preview_voice_sample(
            self.temporary_profile_name, new_text
        )

    async def attempt_save(self) -> VoiceCloneSaveResult | None:
        candidate_name = self.query_one("#save-profile-name-input", Input).value.strip()
        error_label = self.query_one("#save-name-error", Label)

        if not candidate_name:
            error_label.update("Name cannot be empty.")
            error_label.remove_class("hidden")
            return None

        if candidate_name != self.temporary_profile_name:
            try:
                await asyncio.to_thread(
                    self.settings_repository.rename_voice_profile,
                    self.temporary_profile_name,
                    candidate_name,
                )
            except FileExistsError as e:
                error_label.update(str(e))
                error_label.remove_class("hidden")
                return None
            self.temporary_profile_name = candidate_name

        error_label.add_class("hidden")
        set_as_active = self.query_one("#save-active-toggle", Switch).value
        return VoiceCloneSaveResult(
            profile_name=candidate_name, set_as_active=set_as_active
        )


class FilePickPhase(Static):
    def compose(self):
        with Vertical(classes="voice-clone-body"):
            with Center():
                yield WidgetButton("Clone Voice", id="clone-voice-button")
            with Center():
                yield Label(
                    "Selected file: ", id="selected-file-label", classes="hidden"
                )


class PhaseBar(Static):
    phase = 1

    def compose(self):
        with Vertical(classes="voice-clone-phase-bar"):
            with Horizontal(classes="voice-clone-phase-dots"):
                yield Label("●───────", id="phase-dot-1")
                yield Label("○───────", id="phase-dot-2")
                yield Label("○", id="phase-dot-3")

            with Horizontal(classes="voice-clone-phase-labels"):
                yield Label("FILE", classes="-active phase file-phase")
                yield Label("ANALYSIS", classes="phase analysis-phase")
                yield Label("SAVE", classes="phase save-phase")

    def phase_next(self):
        self.phase += 1
        self.query(".phase.-active").remove_class("-active")
        if self.phase < 3:
            self.query_one("#phase-dot-2", Label).update("●───────")
            self.query_one(".analysis-phase").add_class("-active")
        if self.phase >= 3:
            self.query_one(".save-phase").add_class("-active")
            self.query_one("#phase-dot-3", Label).update("●")

    def phase_reset(self):
        self.phase = 1
        self.query(".phase.-active").remove_class("-active")
        self.query_one(".file-phase").add_class("-active")
        self.query_one("#phase-dot-2", Label).update("○───────")
        self.query_one("#phase-dot-3", Label).update("○")


class VoiceCloneModalScreen(ModalScreen[VoiceCloneSaveResult | None]):
    phase = 1
    file_path: Path | None = None

    @inject
    def __init__(
        self,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.settings_repository = settings_repository

    def on_mount(self):
        self.border_title = "CLONE VOICE FROM FILE"

    def compose(self):
        with Vertical():
            yield PhaseBar()
            with Center(classes="voice-clone-body"):
                yield FilePickPhase()
            with Horizontal(classes="voice-clone-footer"):
                with Horizontal(classes="voice-clone-footer-left"):
                    yield WidgetButton("X Cancel", id="voice-clone-cancel-button")
                with Horizontal(classes="voice-clone-footer-center"):
                    pick_another_button = WidgetButton(
                        "← Pick another", id="voice-clone-pick-another-button"
                    )
                    pick_another_button.add_class("hidden")
                    yield pick_another_button
                with Horizontal(classes="voice-clone-footer-right"):
                    next_button = WidgetButton("Next →", id="voice-clone-next-button")
                    next_button.disabled = True
                    yield next_button

    @on(Button.Pressed, "#clone-voice-button")
    def handle_clone_voice_pressed(self) -> None:
        self.app.push_screen(
            FileOpen(
                filters=Filters(
                    ("MP3", lambda file_path: file_path.suffix == ".mp3"),
                    ("WAV", lambda file_path: file_path.suffix == ".wav"),
                )
            ),
            callback=self.handle_file_selected,
        )

    def handle_file_selected(self, opened: Path | None) -> None:
        if opened is None:
            return
        self.file_path = opened
        self.query_one("#selected-file-label", Label).update(f"Selected file: {opened}")
        self.query_one("#selected-file-label").remove_class("hidden")
        self.query_one("#voice-clone-next-button", WidgetButton).disabled = False

    def cleanup_unsaved_clone(self) -> None:
        if self.phase == 3 and self.file_path is not None:
            self.settings_repository.remove_voice_profile(self.file_path.stem)

    @on(Button.Pressed, "#voice-clone-cancel-button")
    def handle_cancel_pressed(self) -> None:
        self.cleanup_unsaved_clone()
        self.dismiss(None)

    @on(Button.Pressed, "#voice-clone-pick-another-button")
    def handle_pick_another_pressed(self) -> None:
        self.cleanup_unsaved_clone()
        self.phase = 1
        self.file_path = None
        self.query_one("#voice-clone-next-button", WidgetButton).disabled = True
        self.query_one("#voice-clone-pick-another-button").add_class("hidden")
        self.query_one(".voice-clone-body").remove_children()
        self.query_one(".voice-clone-body").mount(FilePickPhase())
        self.query_one(PhaseBar).phase_reset()

    @on(Button.Pressed, "#voice-clone-next-button")
    def handle_next_pressed(self) -> None:
        if self.phase == 3:
            self.save_and_dismiss()
            return

        self.phase += 1
        if self.file_path is None:
            return
        self.query_one(PhaseBar).phase_next()
        self.query_one(".voice-clone-body").remove_children()
        if self.phase == 2:
            self.query_one("#voice-clone-next-button", WidgetButton).disabled = True
            self.query_one("#voice-clone-pick-another-button").remove_class("hidden")
            self.query_one(".voice-clone-body").mount(
                AnalysisPhase(self.file_path, self.settings_repository)
            )
        elif self.phase == 3:
            self.query_one("#voice-clone-next-button", WidgetButton).disabled = True
            self.query_one("#voice-clone-pick-another-button").add_class("hidden")
            self.query_one(".voice-clone-body").mount(
                SavePhase(self.file_path, self.settings_repository)
            )

    def on_analysis_phase_analysis_completed(
        self, message: AnalysisPhase.AnalysisCompleted
    ) -> None:
        self.query_one(
            "#voice-clone-next-button", WidgetButton
        ).disabled = not message.is_valid

    def on_save_phase_cloning_completed(
        self, message: SavePhase.CloningCompleted
    ) -> None:
        next_button = self.query_one("#voice-clone-next-button", WidgetButton)
        pick_another_button = self.query_one(
            "#voice-clone-pick-another-button", WidgetButton
        )
        if message.is_successful:
            next_button.label = Content("[✓ Save profile]")
            next_button.disabled = False
            pick_another_button.label = Content("[← Another file]")
            pick_another_button.remove_class("hidden")
        else:
            pick_another_button.remove_class("hidden")

    @work
    async def save_and_dismiss(self) -> None:
        save_phase = self.query_one(SavePhase)
        result = await save_phase.attempt_save()
        if result is not None:
            self.dismiss(result)
