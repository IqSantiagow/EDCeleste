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


class ChatterboxTTSInputWidgetIds(enum.Enum):
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
        super().__init__(*args, **kwargs)
        self.chatterbox_provider = chatterbox_provider
        self.settings_repository = settings_repository

    def on_mount(self) -> None:
        self.call_later(self.fetch_profiles)

    def compose(self) -> ComposeResult:
        if self.voice_profiles is None:
            yield LoadingIndicator(id="loading-voice-profiles-indicator")
        else:
            yield WidgetLabeledSelectRow(
                "Voice: ",
                self.voice_profiles,
                self.chatterbox_provider.profile,
                id=ChatterboxTTSInputWidgetIds.TTS_PROFILE_INPUT.value,
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
                id=ChatterboxTTSInputWidgetIds.TTS_EXAGGERATION_INPUT.value,
            )
            yield WidgetLabeledSliderRow(
                "Pace (cfg):",
                0,
                1,
                self.chatterbox_provider.cfg_weight,
                step=0.05,
                id=ChatterboxTTSInputWidgetIds.TTS_CFG_WEIGHT_INPUT.value,
            )
            yield WidgetLabeledSelectRow(
                "Device: ",
                CHATTERBOX_DEVICE_OPTIONS,
                self.chatterbox_provider.device,
                id=ChatterboxTTSInputWidgetIds.TTS_DEVICE_INPUT.value,
            )
            yield WidgetLabeledSwitchRow(
                "Nano model:",
                self.chatterbox_provider.nano,
                id=ChatterboxTTSInputWidgetIds.TTS_NANO_INPUT.value,
            )

    def fetch_profiles(self) -> None:
        self.voice_profiles = self.settings_repository.get_available_voice_profiles()

    def on_profile_row_profile_deleted(self, message: "ProfileRow.ProfileDeleted"):
        self.fetch_profiles()

    @on(Button.Pressed, "#clone-voice-button")
    def handle_button_pressed(self, event: WidgetButton.Pressed) -> None:
        self.app.push_screen(
            VoiceCloneModalScreen(), callback=self.handle_voice_clone_dismissed
        )
        self.log("Clone voice button pressed")

    def handle_voice_clone_dismissed(self, result: VoiceCloneSaveResult | None) -> None:
        if result is None:
            return
        self.apply_voice_clone_result(result)

    @work
    async def apply_voice_clone_result(self, result: VoiceCloneSaveResult) -> None:
        self.fetch_profiles()

        await self.recompose()

        if result.set_as_active:
            select = self.query_one(
                f"#{ChatterboxTTSInputWidgetIds.TTS_PROFILE_INPUT.value} Select", Select
            )
            select.value = result.profile_name


class ProfileRow(Horizontal):
    DEFAULT_CLASSES = "profile-row"

    class ProfileDeleted(Message):
        def __init__(self, profile_name: str) -> None:
            super().__init__()
            self.profile_name = profile_name

    def __init__(
        self,
        profile_name: str,
        settings_repository: SettingsRepository,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.profile_name = profile_name
        self.settings_repository = settings_repository

    def compose(self) -> ComposeResult:
        yield Label(
            "⧉ " + self.profile_name.removesuffix(".pt"), classes="profile-name"
        )
        yield WidgetButton("▶", classes="profile-play-button")
        yield WidgetButton("✖", classes="profile-delete-button")

    @on(Button.Pressed, ".profile-play-button")
    def handle_play_pressed(self) -> None:
        self.play_sample()

    @on(Button.Pressed, ".profile-delete-button")
    def handle_delete_pressed(self) -> None:
        self.settings_repository.remove_voice_profile(self.profile_name)
        self.post_message(self.ProfileDeleted(self.profile_name))
        self.remove()

    @work
    async def play_sample(self) -> None:
        try:
            await self.settings_repository.play_sample_voice(self.profile_name)
        except FileNotFoundError:
            self.notify(f"No sample audio found for '{self.profile_name}'.")
