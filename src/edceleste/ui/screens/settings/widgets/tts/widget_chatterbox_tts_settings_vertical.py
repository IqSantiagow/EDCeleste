import enum

from textual import on, work
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Label, LoadingIndicator, Select, Static
from dependency_injector.wiring import inject, Provide
from edceleste.containers.main_container import Container
from edceleste.services.models.settings_model import ChatterboxTTSProviderModel
from textual.app import ComposeResult

from edceleste.ui.screens.settings.settings_repository import SettingsRepository
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.screens.settings.widgets.tts.voice_clone_modal_screen import (
    VoiceCloneModalScreen,
    VoiceCloneSaveResult,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

CHATTERBOX_DEVICE_OPTIONS = ["auto", "cuda", "cpu"]


class ChatterboxTTSInputWidgetIds(enum.StrEnum):
    TTS_PROFILE_INPUT = "tts-profile-input"
    TTS_EXAGGERATION_INPUT = "tts-exaggeration-input"
    TTS_CFG_WEIGHT_INPUT = "tts-cfg-weight-input"
    TTS_DEVICE_INPUT = "tts-device-input"
    TTS_NANO_INPUT = "tts-nano-input"


class WidgetChatterboxTTSSettingsVertical(Vertical):
    voice_profiles: reactive[list[str] | None] = reactive(None, recompose=True)

    @inject
    def __init__(
        self,
        chatterbox_provider: ChatterboxTTSProviderModel,
        settings_repository: SettingsRepository = Provide[
            Container.settings_repository
        ],
        *args,
        **kwargs,
    ) -> None:
        """Only reads chatterbox_provider. The changes go up as ValueChanged
        and WidgetTTSContainer writes them."""
        super().__init__(*args, **kwargs)
        self.chatterbox_provider = chatterbox_provider
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        """Loads the voice profile list right after mounting. Until then
        compose() shows a loading indicator."""
        self.call_later(self.fetch_profiles)

    def compose(self) -> ComposeResult:
        """Runs again every time voice_profiles is set.

        Loaded: the voice select, one row per cloned profile (with play and
        delete buttons), the clone button, then the Chatterbox params
        (exaggeration, pace, device, nano model).
        """
        if self.voice_profiles is None:
            yield LoadingIndicator(id="loading-voice-profiles-indicator")
        else:
            yield WidgetLabeledSelectRow(
                "Voice: ",
                self.voice_profiles,
                self.chatterbox_provider.profile,
                id=ChatterboxTTSInputWidgetIds.TTS_PROFILE_INPUT,
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
                    id=f"profile-row-{profile.removesuffix('.pt')}",
                )

            yield WidgetButton("+ Clone voice from file...", id="clone-voice-button")

            yield WidgetSectionHeader("CHATTERBOX PARAMS")

            yield WidgetLabeledSliderRow(
                "Exaggeration:",
                0,
                2,
                self.chatterbox_provider.exaggeration,
                step=0.1,
                id=ChatterboxTTSInputWidgetIds.TTS_EXAGGERATION_INPUT,
            )
            yield WidgetLabeledSliderRow(
                "Pace (cfg):",
                0,
                1,
                self.chatterbox_provider.cfg_weight,
                step=0.05,
                id=ChatterboxTTSInputWidgetIds.TTS_CFG_WEIGHT_INPUT,
            )
            yield WidgetLabeledSelectRow(
                "Device: ",
                CHATTERBOX_DEVICE_OPTIONS,
                self.chatterbox_provider.device,
                id=ChatterboxTTSInputWidgetIds.TTS_DEVICE_INPUT,
            )
            yield WidgetLabeledSwitchRow(
                "Nano model:",
                self.chatterbox_provider.nano,
                id=ChatterboxTTSInputWidgetIds.TTS_NANO_INPUT,
            )

    def fetch_profiles(self) -> None:
        """Reads the profile names from the voices folder on disk. Setting
        voice_profiles recomposes this block. The list comes from the saved TTS
        engine, so it is empty while the saved engine is not Chatterbox."""
        self.voice_profiles = self.settings_repository.get_available_voice_profiles()

    def on_profile_row_profile_deleted(self, message: "ProfileRow.ProfileDeleted"):
        """A ProfileRow deleted its profile files, so the voice select must
        drop that name. Reloads the list, which recomposes the block. The
        provider keeps the deleted name if it was the active voice."""
        self.fetch_profiles()

    @on(Button.Pressed, "#clone-voice-button")
    def open_voice_clone_modal(self, event: WidgetButton.Pressed) -> None:
        """Opens VoiceCloneModalScreen on top of the settings. When the modal
        closes, handle_voice_clone_dismissed() gets its result."""
        self.app.push_screen(
            VoiceCloneModalScreen(), callback=self.handle_voice_clone_dismissed
        )
        self.log("Clone voice button pressed")

    def handle_voice_clone_dismissed(self, result: VoiceCloneSaveResult | None) -> None:
        """None means the pilot cancelled the modal, nothing to do. Otherwise
        the new profile is shown in a worker."""
        if result is None:
            return
        self.apply_voice_clone_result(result)

    @work
    async def apply_voice_clone_result(self, result: VoiceCloneSaveResult) -> None:
        """Worker.
        1. Reloads the profile list and waits for the recompose, so the new
           profile is in the voice select.
        2. With set_as_active, picks it in the select. That posts
           ValueChanged, so the provider gets the new profile like after a
           manual pick.
        """
        self.fetch_profiles()

        await self.recompose()

        if result.set_as_active:
            select = self.query_one(
                f"#{ChatterboxTTSInputWidgetIds.TTS_PROFILE_INPUT} Select", Select
            )
            select.value = result.profile_name


class ProfileRow(Horizontal):
    DEFAULT_CLASSES = "profile-row"

    class ProfileDeleted(Message):
        def __init__(self, profile_name: str) -> None:
            """Posted after the profile files were deleted from disk.
            WidgetChatterboxTTSSettingsVertical reloads the list on it."""
            super().__init__()
            self.profile_name = profile_name

    def __init__(
        self,
        profile_name: str,
        settings_repository: SettingsRepository,
        *args,
        **kwargs,
    ) -> None:
        """profile_name is the name without ".pt", as it is shown in the voice
        select."""
        super().__init__(*args, **kwargs)
        self.profile_name = profile_name
        self.settings_repository = settings_repository

    def compose(self) -> ComposeResult:
        """The profile name with a "⧉" in front, a play and a delete button."""
        yield Label(
            "⧉ " + self.profile_name.removesuffix(".pt"), classes="profile-name"
        )
        yield WidgetButton("▶", classes="profile-play-button")
        yield WidgetButton("✖", classes="profile-delete-button")

    @on(Button.Pressed, ".profile-play-button")
    def handle_play_pressed(self) -> None:
        """The ▶ button. Playing runs in a worker, so the UI does not wait for
        the sound."""
        self.play_sample()

    @on(Button.Pressed, ".profile-delete-button")
    def handle_delete_pressed(self) -> None:
        """The ✖ button. No confirmation.
        1. Deletes the profile and its demo sample from disk.
        2. Posts ProfileDeleted to the parent block.
        3. Removes this row.
        """
        self.settings_repository.remove_voice_profile(self.profile_name)
        self.post_message(self.ProfileDeleted(self.profile_name))
        self.remove()

    @work
    async def play_sample(self) -> None:
        """Worker. Plays the demo sample saved with the profile when it was
        cloned, through the speakers. No sample file -> a notification."""
        try:
            await self.settings_repository.play_sample_voice(self.profile_name)
        except FileNotFoundError:
            self.notify(f"No sample audio found for '{self.profile_name}'.")
