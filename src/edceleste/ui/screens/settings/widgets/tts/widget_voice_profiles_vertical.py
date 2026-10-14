import enum

from textual import on, work
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Label, LoadingIndicator, Select, Static
from dependency_injector.wiring import inject, Provide
from edceleste.containers.main_container import Container
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.models.settings_model import TtsProviderParams
from textual.app import ComposeResult

from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.tts.voice_clone_modal_screen import (
    VoiceCloneModalScreen,
    VoiceCloneSaveResult,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader


class VoiceProfileInputWidgetIds(enum.StrEnum):
    TTS_PROFILE_INPUT = "tts-profile-input"


class WidgetVoiceProfilesVertical(Vertical):
    voice_profiles: reactive[list[str] | None] = reactive(None, recompose=True)

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
        """Keeps params (the engine on the screen, saved or not) and the
        repository. Loads nothing yet: voice_profiles stays None, and compose()
        shows a loading indicator, until on_mount() reads the profile names.
        params is the live object of the screen and is never changed here, a
        picked profile goes up as ValueChanged and WidgetTTSContainer writes it
        into params."""
        super().__init__(*args, **kwargs)
        self.params = params
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        """Reads the voice profile names from the voices folder of the engine
        right after mounting, in the UI thread. The read is quick and cannot
        fail for a missing folder (the list is just empty), so the loading
        indicator of compose() never stays."""
        self.call_later(self.reload_profile_names_from_disk)

    def compose(self) -> ComposeResult:
        """Runs again every time voice_profiles is set.

        Not loaded yet (voice_profiles is None): only a loading indicator.
        Loaded: the voice select (id tts-profile-input) with the profile names,
        showing the profile named in params, or nothing when that name is not
        in the list (e.g. its file is gone); then one row per cloned profile
        with play and delete buttons, or the hint "No cloned profiles found"
        when there is none; then the clone button (id clone-voice-button).
        """
        if self.voice_profiles is None:
            yield LoadingIndicator(id="loading-voice-profiles-indicator")
        else:
            yield WidgetLabeledSelectRow(
                "Voice: ",
                self.voice_profiles,
                getattr(self.params, "profile"),
                id=VoiceProfileInputWidgetIds.TTS_PROFILE_INPUT,
            )

            yield WidgetSectionHeader("CLONED PROFILES")

            if not self.voice_profiles:
                yield Static(
                    "No cloned profiles found. Use the button below to clone a new "
                    "voice profile.",
                    classes="no-profiles-message",
                )
            for profile in self.voice_profiles:
                yield ProfileRow(
                    profile,
                    self.settings_repository,
                    self.params,
                    id=f"profile-row-{profile}",
                )

            yield WidgetButton("+ Clone voice from file...", id="clone-voice-button")

    def reload_profile_names_from_disk(self) -> None:
        """Reads the profile names from the voices folder of the engine on disk.
        Setting voice_profiles recomposes this block. The list comes from the
        engine picked on the screen, saved or not."""
        self.voice_profiles = self.settings_repository.get_available_voice_profiles(
            self.params
        )

    def on_profile_row_profile_deleted(
        self, message: "ProfileRow.ProfileDeleted"
    ) -> None:
        """A ProfileRow deleted its profile files, so the voice select must
        drop that name. Reloads the list, which recomposes the block. The
        profile name in params is not changed: when the deleted profile was
        the picked voice, the select shows nothing until the pilot picks
        another one, and saving the settings before that fails with "Profile
        '<name>' does not exist." The message is not stopped, it bubbles up."""
        self.reload_profile_names_from_disk()

    @on(Button.Pressed, "#clone-voice-button")
    def open_voice_clone_modal(self, event: WidgetButton.Pressed) -> None:
        """Opens VoiceCloneModalScreen on top of the settings, for the engine
        on the screen. When the modal closes, its result goes to
        show_cloned_profile_unless_clone_window_was_cancelled()."""
        self.app.push_screen(
            VoiceCloneModalScreen(self.params),
            callback=self.show_cloned_profile_unless_clone_window_was_cancelled,
        )
        self.log("Clone voice button pressed")

    def show_cloned_profile_unless_clone_window_was_cancelled(
        self, result: VoiceCloneSaveResult | None
    ) -> None:
        """None means the pilot cancelled the modal, nothing to do. Otherwise
        the new profile is shown in a worker."""
        if result is None:
            return
        self.reload_profiles_and_pick_the_cloned_one_if_asked(result)

    @work
    async def reload_profiles_and_pick_the_cloned_one_if_asked(
        self, result: VoiceCloneSaveResult
    ) -> None:
        """Worker (@work starts it and gives back a Worker, not None).
        1. Reloads the profile list and waits for the recompose, so the new
           profile is in the voice select.
        2. With result.set_as_active, picks it in the select. That posts
           ValueChanged, so WidgetTTSContainer writes the new profile into the
           settings on the screen, like after a manual pick. Nothing is saved
           until the pilot saves the settings.
        Without set_as_active the new profile only appears in the list.
        """
        self.reload_profile_names_from_disk()

        await self.recompose()

        if result.set_as_active:
            select = self.query_one(
                f"#{VoiceProfileInputWidgetIds.TTS_PROFILE_INPUT} Select", Select
            )
            select.value = result.profile_name


class ProfileRow(Horizontal):
    DEFAULT_CLASSES = "profile-row"

    class ProfileDeleted(Message):
        def __init__(self, profile_name: str) -> None:
            """Posted after the profile files were deleted from disk.
            WidgetVoiceProfilesVertical reloads the list on it."""
            super().__init__()
            self.profile_name = profile_name

    def __init__(
        self,
        profile_name: str,
        settings_repository: SettingsRepository,
        params: TtsProviderParams,
        *args,
        **kwargs,
    ) -> None:
        """profile_name is the name without the file extension, as it is shown
        in the voice select. params are the TTS settings from the screen, saved
        or not (the live object, not a copy). settings_repository plays the
        sample and deletes the profile files for this row."""
        super().__init__(*args, **kwargs)
        self.profile_name = profile_name
        self.settings_repository = settings_repository
        self.params = params

    def compose(self) -> ComposeResult:
        """The profile name with a "⧉" in front, a play and a delete button."""
        yield Label("⧉ " + self.profile_name, classes="profile-name")
        yield WidgetButton("▶", classes="profile-play-button")
        yield WidgetButton("✖", classes="profile-delete-button")

    @on(Button.Pressed, ".profile-play-button")
    def handle_play_pressed(self) -> None:
        """The ▶ button. Starts play_the_sample_saved_with_this_profile() in a
        worker, so the UI does not wait for the sound. Pressing it again while
        a sample plays starts a second one on top of it."""
        self.play_the_sample_saved_with_this_profile()

    @on(Button.Pressed, ".profile-delete-button")
    def delete_this_profile_and_tell_the_list(self) -> None:
        """The ✖ button. No confirmation.
        1. Deletes the profile and its demo sample from disk. When the engine
           on the screen cannot clone voices, it shows the error as a
           notification and keeps the row.
        2. Posts ProfileDeleted to the parent block.
        3. Removes this row.
        """
        try:
            self.settings_repository.remove_voice_profile(
                self.profile_name, self.params
            )
        except VoiceCloningException as e:
            self.notify(str(e), severity="error")
            return
        self.post_message(self.ProfileDeleted(self.profile_name))
        self.remove()

    @work
    async def play_the_sample_saved_with_this_profile(self) -> None:
        """Worker. Plays the demo sample saved with the profile when it was
        cloned, through the speakers, at the saved volume and without Voice Lab
        effects, and returns when the sound ends. No sample file -> a
        notification. An engine that cannot clone voices -> its error as a
        notification. Other errors (e.g. no audio device) are not caught."""
        try:
            await self.settings_repository.play_sample_voice(
                self.profile_name, self.params
            )
        except FileNotFoundError:
            self.notify(f"No sample audio found for '{self.profile_name}'.")
        except VoiceCloningException as e:
            self.notify(str(e), severity="error")
