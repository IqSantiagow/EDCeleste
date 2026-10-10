import asyncio
import re
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
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.models.settings_model import TtsProviderParams
from edceleste.services.models.voice_cloning_models import VoiceAnalysisResult
from edceleste.services.tts_service import DEFAULT_VOICE_SAMPLE_TEXT
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


def pick_free_profile_name(wanted_name: str, taken_names: list[str]) -> str:
    """wanted_name when no profile has it yet, otherwise the first free one of
    "<wanted_name>_1", "<wanted_name>_2" and so on. Reads nothing from disk,
    taken_names is the list of saved profiles."""
    free_name = wanted_name
    number = 1
    while free_name in taken_names:
        free_name = f"{wanted_name}_{number}"
        number += 1
    return free_name


def format_seconds_as_clock(seconds: float) -> str:
    """75.25 -> "01:15.2". Minutes are not capped at 60, there are no
    hours."""
    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes:02d}:{remaining_seconds:04.1f}"


class AnalysisCheckRow(Horizontal):
    DEFAULT_CLASSES = "analysis-check-row"

    def __init__(self, label: str, value: str, is_ok: bool, hint: str = "", **kwargs):
        """One line of the sample analysis, e.g. "Duration  12.3s". is_ok
        picks the icon, hint is the grey text after the value."""
        super().__init__(**kwargs)
        self.check_label = label
        self.check_value = value
        self.is_ok = is_ok
        self.check_hint = hint

    def compose(self):
        """A green ✓ or a red ✗, then label, value and hint."""
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
            """Posted when the sample analysis finishes. is_valid False (sample
            shorter than the provider needs, 10 s for Chatterbox) keeps the
            modal's Next button disabled."""
            super().__init__()
            self.is_valid = is_valid

    def __init__(
        self,
        file_path: Path,
        settings_repository: SettingsRepository,
        params: TtsProviderParams,
    ):
        """Step 2 of the modal. analysis stays None until run_analysis()
        finishes, compose() shows "Analyzing sample..." until then. params are
        the TTS settings from the screen, they say how long a sample must
        be."""
        self.file_path = file_path
        self.settings_repository = settings_repository
        self.params = params
        self.analysis: VoiceAnalysisResult | None = None
        super().__init__()

    def on_mount(self):
        """Starts the analysis as soon as the step is shown."""
        self.run_analysis()

    @work
    async def run_analysis(self) -> None:
        """Worker.
        1. Reads and measures the audio file in a thread, so the UI does not
           freeze.
        2. Posts AnalysisCompleted to the modal, which enables Next for a
           valid sample.
        3. Recomposes to show the results.
        """
        analysis = await asyncio.to_thread(
            self.settings_repository.analyze_voice_sample,
            str(self.file_path),
            self.params,
        )
        self.analysis = analysis
        self.post_message(self.AnalysisCompleted(analysis["is_valid"]))
        await self.recompose()

    def compose(self):
        """Before the analysis only "Analyzing sample...". After it: file name
        and folder, the waveform with its length, the check rows, a play
        button, and a red hint when the sample is not valid."""
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
        """Duration, channels, sample rate, peak and noise floor. Only the
        duration can fail, the others are always ✓ and only informative."""
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
        """The ▶ Play button under the analysis."""
        self.play_selected_file()

    @work
    async def play_selected_file(self) -> None:
        """Worker. Plays the picked audio file through the speakers, as it
        is, without the clone."""
        await self.settings_repository.play_audio_file(str(self.file_path))


class CloningStepRow(Horizontal):
    """One line in the cloning checklist: ○ pending -> spinner active -> ✓/✗ done."""

    DEFAULT_CLASSES = "analysis-check-row"

    def __init__(self, label: str, **kwargs):
        """label is one entry of CLONING_STEP_LABELS."""
        super().__init__(**kwargs)
        self.step_label = label

    def compose(self):
        """Starts as pending: the "○" icon, with a hidden spinner next to
        it."""
        yield Label("○", classes="analysis-check-icon warning-label", id="step-icon")
        yield WidgetSpinner(classes="analysis-check-icon hidden", id="step-spinner")
        yield Label(self.step_label, classes="analysis-check-label")

    def mark_active(self) -> None:
        """Hides the "○" and shows a running spinner in its place."""
        self.query_one("#step-icon", Label).add_class("hidden")
        spinner = self.query_one("#step-spinner", WidgetSpinner)
        spinner.remove_class("hidden")
        spinner.start()

    def mark_done(self) -> None:
        """Stops the spinner and shows a green ✓."""
        self._show_icon("✓", "success")

    def mark_failed(self) -> None:
        """Stops the spinner and shows a red ✗."""
        self._show_icon("✗", "error")

    def _show_icon(self, icon: str, status_class: str) -> None:
        """Puts icon into the "○" label and shows it again. status_class
        "success" or "error" colours it."""
        spinner = self.query_one("#step-spinner", WidgetSpinner)
        spinner.stop()
        spinner.add_class("hidden")
        step_icon = self.query_one("#step-icon", Label)
        step_icon.update(icon)
        step_icon.set_classes(f"analysis-check-icon warning-label {status_class}")


class SavePhase(Static):
    class CloningCompleted(Message):
        def __init__(self, is_successful: bool) -> None:
            """Posted when cloning ends, good or bad. The modal turns Next into
            [✓ Save profile] only when is_successful, and always shows
            [← Another file]."""
            super().__init__()
            self.is_successful = is_successful

    # Flips from the cloning checklist to the "name it and try it" view once
    # clone_voice() finishes - recompose=True redraws compose() on flip.
    is_ready: reactive[bool] = reactive(False, recompose=True)

    def __init__(
        self,
        file_path: Path,
        settings_repository: SettingsRepository,
        params: TtsProviderParams,
    ):
        """Step 3 of the modal. The profile is first cloned under the file name
        without extension, e.g. "celeste.wav" -> "celeste". When a saved
        profile already has that name, it gets "_1", "_2"... instead
        ("celeste_1"), so an existing voice is never replaced. Reads the saved
        profile names from disk, in the UI thread (one folder listing). When
        the engine of params cannot clone, that list is empty and the file
        name is used as it is. params are the TTS settings from the screen
        (saved or not), the cloning and the preview use them, not the saved
        ones."""
        self.file_path = file_path
        self.params = params
        # The name the profile already lives under on disk since clone_voice()
        # ran. The user can rename it before saving, see
        # rename_clone_to_typed_name().
        self.temporary_profile_name = pick_free_profile_name(
            file_path.stem, settings_repository.get_available_voice_profiles(params)
        )
        self.settings_repository = settings_repository
        super().__init__()

    def on_mount(self):
        """Starts cloning as soon as the step is shown."""
        self.run_clone_voice()

    def compose(self):
        """Not ready: "<file> → <profile name>" and one CloningStepRow per
        step. Ready: the view from _compose_ready_view()."""
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
        """Shown after a successful clone:
        - the profile name input (prefilled) and a hidden error line for it,
        - the "Set as active" switch, on by default,
        - A/B buttons to compare the source file with the demo sample,
        - a sample text input and a regenerate button to hear the clone say
          any text.
        """
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
        """Worker. Clones the voice with the engine of params (the settings on
        the screen) and saves the profile and a demo sample to disk under
        temporary_profile_name.

        Every state the repository yields ticks the current step ✓ and starts
        the spinner on the next one. On error the current step gets ✗, the
        error text is added under the steps and CloningCompleted(False) is
        posted. On success is_ready flips, which recomposes into the ready
        view, and CloningCompleted(True) is posted.
        """
        steps = list(self.query(CloningStepRow))
        step_index = 0
        steps[step_index].mark_active()

        try:
            async for _cloning_state in self.settings_repository.clone_voice(
                str(self.file_path), self.temporary_profile_name, self.params
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
        """The "A source file" ▶ button."""
        self.play_source()

    @on(Button.Pressed, "#compare-play-sample-button")
    def handle_play_sample_pressed(self) -> None:
        """The "B clone synthesis" ▶ button."""
        self.play_sample()

    @work(exclusive=True, group="ab-playback")
    async def play_source(self) -> None:
        """Worker. Plays the original picked file. Shares the "ab-playback"
        group with the other two players, so a new press cancels the
        running one."""
        await self.settings_repository.play_audio_file(str(self.file_path))

    @work(exclusive=True, group="ab-playback")
    async def play_sample(self) -> None:
        """Worker. Plays the demo sample saved by cloning, not a new synthesis.
        Same "ab-playback" group as play_source()."""
        await self.settings_repository.play_sample_voice(self.temporary_profile_name)

    @on(Button.Pressed, "#save-regenerate-button")
    def handle_regenerate_pressed(self) -> None:
        """The ↻ Regenerate button."""
        self.preview_sample_with_custom_text()

    @work(exclusive=True, group="ab-playback")
    async def preview_sample_with_custom_text(self) -> None:
        """Worker. Makes the cloned voice say the text from the sample text
        input and plays it. It runs the Chatterbox model, so it is slow, and
        it saves nothing. Same "ab-playback" group as play_source()."""
        new_text = self.query_one("#save-sample-text-input", Input).value
        await self.settings_repository.preview_voice_sample(
            self.temporary_profile_name, new_text, self.params
        )

    async def rename_clone_to_typed_name(self) -> VoiceCloneSaveResult | None:
        """Called by the modal's [✓ Save profile] button. The profile is
        already on disk under temporary_profile_name, so "saving" only means
        giving it the name typed in the input:
        1. empty name -> error under the input, returns None,
        2. a changed name with other characters than letters, digits, spaces,
           "-" and "_" (e.g. "../x") -> error under the input, returns None,
        3. a changed name -> renames the profile and its sample on disk in a
           thread. A taken name or an engine that cannot clone -> error under
           the input, returns None,
        4. returns the final name and the "Set as active" switch value.
        None always means: the error is shown, the modal stays open and the
        clone keeps its old name. Never picks a free name itself.
        """
        candidate_name = self.query_one("#save-profile-name-input", Input).value.strip()
        error_label = self.query_one("#save-name-error", Label)

        if not candidate_name:
            error_label.update("Name cannot be empty.")
            error_label.remove_class("hidden")
            return None

        is_new_name = candidate_name != self.temporary_profile_name
        if is_new_name and not re.fullmatch(r"[\w\- ]+", candidate_name):
            error_label.update("Use only letters, digits, spaces, - and _.")
            error_label.remove_class("hidden")
            return None

        if is_new_name:
            try:
                await asyncio.to_thread(
                    self.settings_repository.rename_voice_profile,
                    self.temporary_profile_name,
                    candidate_name,
                    self.params,
                )
            except (FileExistsError, VoiceCloningException) as e:
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
        """Step 1 of the modal. The "Clone Voice" button opens the file picker,
        the hidden label shows the picked file afterwards. The modal screen
        handles both."""
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
        """Three dots joined by lines over FILE, ANALYSIS and SAVE. Starts on
        FILE."""
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
        """Moves the highlight one step right and fills the dot of the new
        step. It never goes past SAVE."""
        self.phase += 1
        self.query(".phase.-active").remove_class("-active")
        if self.phase < 3:
            self.query_one("#phase-dot-2", Label).update("●───────")
            self.query_one(".analysis-phase").add_class("-active")
        if self.phase >= 3:
            self.query_one(".save-phase").add_class("-active")
            self.query_one("#phase-dot-3", Label).update("●")

    def phase_reset(self):
        """Back to FILE: highlight on FILE, dots 2 and 3 empty again."""
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
        params: TtsProviderParams,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        """A three step wizard: 1 pick a file, 2 analyse it, 3 clone and name
        it. phase holds the current step. Dismissed with a
        VoiceCloneSaveResult after a save, or with None on cancel. params are
        the TTS settings as they are on the screen, the pilot has not saved
        them yet, so the steps get them from here and not from the saved
        settings."""
        super().__init__(*args, **kwargs)
        self.params = params
        self.settings_repository = settings_repository

    def on_mount(self):
        """Sets the title drawn in the modal border."""
        self.border_title = "CLONE VOICE FROM FILE"

    def compose(self):
        """Phase bar on top, the step body in the middle (FilePickPhase at the
        start) and the footer: [X Cancel], a hidden [← Pick another] and a
        disabled [Next →]."""
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
        """The "Clone Voice" button of step 1. Opens a file picker that shows
        only .mp3 and .wav files. The picked path goes to
        handle_file_selected()."""
        self.app.push_screen(
            FileOpen(
                filters=Filters(
                    ("MP3", lambda file_path: file_path.suffix == ".mp3"),
                    ("WAV", lambda file_path: file_path.suffix == ".wav"),
                )
            ),
            callback=self.handle_file_selected,
        )

    def handle_file_selected(self, selected_file_path: Path | None) -> None:
        """None means the pilot closed the picker without a file. Otherwise
        remembers the path, shows it under the button and enables Next."""
        if selected_file_path is None:
            return
        self.file_path = selected_file_path
        self.query_one("#selected-file-label", Label).update(
            f"Selected file: {selected_file_path}"
        )
        self.query_one("#selected-file-label").remove_class("hidden")
        self.query_one("#voice-clone-next-button", WidgetButton).disabled = False

    def cleanup_unsaved_clone(self) -> None:
        """Only in step 3, where cloning already wrote a profile to disk.
        Deletes that profile (under the name SavePhase picked, which is never
        the name of an older voice), so leaving without saving leaves no files
        behind. Steps 1 and 2 wrote nothing. When the engine cannot clone
        voices, the files stay and the error is shown as a notification."""
        save_phases = self.query(SavePhase)
        if self.phase != 3 or not save_phases:
            return

        try:
            self.settings_repository.remove_voice_profile(
                save_phases.first().temporary_profile_name, self.params
            )
        except VoiceCloningException as e:
            self.notify(str(e), severity="error")

    @on(Button.Pressed, "#voice-clone-cancel-button")
    def handle_cancel_pressed(self) -> None:
        """[X Cancel]. Deletes an unsaved clone and closes the modal with
        None."""
        self.cleanup_unsaved_clone()
        self.dismiss(None)

    @on(Button.Pressed, "#voice-clone-pick-another-button")
    def handle_pick_another_pressed(self) -> None:
        """[← Pick another] in step 2 or 3:
        1. deletes an unsaved clone (step 3),
        2. forgets the file and disables Next,
        3. puts FilePickPhase back in the body and resets the phase bar.
        """
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
        """[Next →], in step 3 [✓ Save profile].

        - step 3 -> saves and closes, see save_and_dismiss(),
        - step 1 -> step 2: mounts AnalysisPhase, disables Next until the
          analysis says the sample is valid, shows [← Pick another],
        - step 2 -> step 3: mounts SavePhase, which starts cloning, disables
          Next until cloning ends, hides [← Pick another].
        """
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
                AnalysisPhase(self.file_path, self.settings_repository, self.params)
            )
        elif self.phase == 3:
            self.query_one("#voice-clone-next-button", WidgetButton).disabled = True
            self.query_one("#voice-clone-pick-another-button").add_class("hidden")
            self.query_one(".voice-clone-body").mount(
                SavePhase(self.file_path, self.settings_repository, self.params)
            )

    def on_analysis_phase_analysis_completed(
        self, message: AnalysisPhase.AnalysisCompleted
    ) -> None:
        """Enables Next only for a valid sample."""
        self.query_one(
            "#voice-clone-next-button", WidgetButton
        ).disabled = not message.is_valid

    def on_save_phase_cloning_completed(
        self, message: SavePhase.CloningCompleted
    ) -> None:
        """Success turns Next into an enabled [✓ Save profile]. Success or not,
        [← Pick another] comes back as [← Another file]."""
        next_button = self.query_one("#voice-clone-next-button", WidgetButton)
        pick_another_button = self.query_one(
            "#voice-clone-pick-another-button", WidgetButton
        )
        if message.is_successful:
            next_button.label = Content("[✓ Save profile]")
            next_button.disabled = False
        pick_another_button.label = Content("[← Another file]")
        pick_another_button.remove_class("hidden")

    @work
    async def save_and_dismiss(self) -> None:
        """Worker. Asks SavePhase to give the clone the typed name. None (for
        every reason listed in rename_clone_to_typed_name: empty, not allowed
        characters, taken, engine that cannot clone) keeps the modal open with
        the error shown, otherwise the modal closes and returns the result to
        the Chatterbox settings."""
        save_phase = self.query_one(SavePhase)
        result = await save_phase.rename_clone_to_typed_name()
        if result is not None:
            self.dismiss(result)
