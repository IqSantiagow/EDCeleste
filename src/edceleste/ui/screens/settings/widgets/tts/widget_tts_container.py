import enum

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive

from edceleste.services.models.settings_model import (
    DEFAULT_EDGE_VOICE,
    ChatterboxParamsModel,
    EdgeParamsModel,
    PocketParamsModel,
    TTSModel,
    TtsEngine,
    TtsProviderParams,
)
from edceleste.ui.screens.settings.events.settings_events import SectionSettingsChanged
from edceleste.ui.screens.settings.widgets.const_ids import SettingsSection
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    ValueChanged,
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_switch_row import (
    WidgetLabeledSwitchRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_chatterbox_tts_settings_vertical import (  # noqa: E501
    ChatterboxTTSInputWidgetIds,
    WidgetChatterboxTTSSettingsVertical,
)
from edceleste.ui.screens.settings.widgets.tts.widget_edge_tts_settings_vertical import (  # noqa: E501
    EdgeTTSInputWidgetIds,
    WidgetEdgeTTSSettingsVertical,
)
from edceleste.ui.screens.settings.widgets.tts.widget_voice_profiles_vertical import (  # noqa: E501
    VoiceProfileInputWidgetIds,
    WidgetVoiceProfilesVertical,
)
from edceleste.ui.screens.settings.widgets.tts.widget_voice_test_button import (
    WidgetVoiceTestButton,
)
from edceleste.ui.screens.settings.widgets.widget_base_settings_container import (
    WidgetBaseSettingsContainer,
)
from edceleste.ui.widgets.common.widget_section_header import WidgetSectionHeader

ENGINE_NAMES = {"edge": "Edge TTS", "chatterbox": "Chatterbox", "pocket": "Pocket TTS"}
LOCATION_OPTIONS = ["Local", "Remote"]
LOCATION_VALUES = ["local", "remote"]
# Local engines run on this computer. Remote engines run on a server somewhere
# else. The first engine of a place is the one picked when the pilot switches to
# that place. Pocket TTS comes first because it needs no GPU.
ENGINES_OF_LOCATION: dict[str, list[TtsEngine]] = {
    "local": ["pocket", "chatterbox"],
    "remote": ["edge"],
}


def find_location_of_engine(engine: str) -> str:
    """Says where an engine runs. Takes the engine key in lower case ("edge",
    "chatterbox" or "pocket") and looks it up in ENGINES_OF_LOCATION. Returns
    "local" for an engine on this computer (Pocket TTS, Chatterbox) and
    "remote" for one on a server (Edge TTS). Raises ValueError for any other
    name, also for an empty one. Changes nothing."""
    for location, engines in ENGINES_OF_LOCATION.items():
        if engine in engines:
            return location
    raise ValueError(f"Unknown TTS engine: {engine}")


def build_default_params_for_engine(engine: str) -> TtsProviderParams:
    """Makes a new params object with the defaults of an engine, for the first
    time the pilot switches to it on this screen. Every call gives a new
    object, because on_value_changed() changes the params in place.
    - "edge": the default Edge voice.
    - "pocket": Pocket TTS with an empty profile name (no voice picked).
    - anything else: Chatterbox with an empty profile name and the defaults of
      ChatterboxParamsModel for exaggeration, pace, device and nano model.
    Unlike find_location_of_engine(), a name that is no engine does not raise,
    it gives Chatterbox."""
    if engine == "edge":
        return EdgeParamsModel(type="edge", voice=DEFAULT_EDGE_VOICE)
    if engine == "pocket":
        return PocketParamsModel(type="pocket", profile="")
    return ChatterboxParamsModel(type="chatterbox", profile="")


class TTSInputWidgetIds(enum.StrEnum):
    TTS_LOCATION_INPUT = "tts-location-input"
    TTS_PROVIDER_TYPE_INPUT = "tts-provider-type-input"
    VOLUME_INPUT = "volume-input"
    SHIP_EFFECT_INPUT = "ship-effect-input"


class WidgetTTSContainer(WidgetBaseSettingsContainer):
    DEFAULT_CLASSES = "settings-container"
    BORDER_TITLE = "TEXT TO SPEECH"

    params: reactive[TtsProviderParams | None] = reactive(None, recompose=True)

    def __init__(
        self,
        tts_model: TTSModel,
        *args,
        **kwargs,
    ) -> None:
        """tts_model is part of the screen's working copy of the settings and
        is changed in place. The extra arguments (id, classes...) go to the
        base container, which needs the id "settings-tts".
        1. Starts params_of_every_engine with the params of the saved engine
           only. The params of an engine the pilot visits later are added by
           switch_to_engine_with_remembered_or_default_params(), so switching
           back shows them again.
        2. Remembers the saved engine, for is_modified().
        3. Sets params to tts_model.params without a recompose, because nothing
           is composed yet."""
        super().__init__(*args, **kwargs)
        self.tts_model = tts_model
        self.params_of_every_engine: dict[str, TtsProviderParams] = {
            tts_model.provider: tts_model.params
        }
        self.saved_engine = tts_model.provider
        self.set_reactive(WidgetTTSContainer.params, tts_model.params)

    def compose(self) -> ComposeResult:
        yield from super().compose()
        with VerticalScroll():
            yield WidgetSectionHeader("TTS SETTINGS")
            params = self.params
            assert params is not None, "params must be set before compose() runs"
            location = find_location_of_engine(params.type)
            engines_of_location = ENGINES_OF_LOCATION[location]
            yield WidgetLabeledSelectRow(
                "Location: ",
                LOCATION_OPTIONS,
                location,
                values=LOCATION_VALUES,
                id=TTSInputWidgetIds.TTS_LOCATION_INPUT,
            )
            yield WidgetLabeledSelectRow(
                "Engine: ",
                [ENGINE_NAMES[engine] for engine in engines_of_location],
                params.type,
                values=list(engines_of_location),
                id=TTSInputWidgetIds.TTS_PROVIDER_TYPE_INPUT,
            )
            if isinstance(params, EdgeParamsModel):
                yield from self.compose_edge_tts_settings(params)
            elif isinstance(params, ChatterboxParamsModel):
                yield from self.compose_chatterbox_settings(params)
            elif isinstance(params, PocketParamsModel):
                yield from self.compose_pocket_settings(params)
            yield WidgetLabeledSliderRow(
                "Volume:",
                0,
                1,
                self.tts_model.volume,
                step=0.05,
                id=TTSInputWidgetIds.VOLUME_INPUT,
            )
            yield WidgetLabeledSwitchRow(
                "Ship effect:",
                self.tts_model.ship_effect,
                hint="sounds like inside the ship",
                id=TTSInputWidgetIds.SHIP_EFFECT_INPUT,
            )
            yield WidgetVoiceTestButton(self.tts_model)

    def on_value_changed(self, message: ValueChanged) -> None:
        params = self.params
        assert params is not None, "params must be set before on_value_changed runs"
        match message.sender_id:
            case TTSInputWidgetIds.TTS_LOCATION_INPUT:
                if (
                    message.new_value in ENGINES_OF_LOCATION
                    and message.new_value != find_location_of_engine(params.type)
                ):
                    self.switch_to_engine_with_remembered_or_default_params(
                        ENGINES_OF_LOCATION[message.new_value][0]
                    )
            case TTSInputWidgetIds.TTS_PROVIDER_TYPE_INPUT:
                if (
                    message.new_value in ENGINE_NAMES
                    and message.new_value != params.type
                ):
                    self.switch_to_engine_with_remembered_or_default_params(
                        message.new_value
                    )
            case EdgeTTSInputWidgetIds.VOICE_INPUT:
                if isinstance(params, EdgeParamsModel):
                    params.voice = message.new_value
            case TTSInputWidgetIds.VOLUME_INPUT:
                try:
                    self.tts_model.volume = float(message.new_value)
                except ValueError:
                    self.log(f"Invalid volume value: {message.new_value}")
                    self.notify("Volume must be a number between 0.0 and 1.0.")
                    return
            case VoiceProfileInputWidgetIds.TTS_PROFILE_INPUT:
                if isinstance(params, (ChatterboxParamsModel, PocketParamsModel)):
                    params.profile = message.new_value
            case ChatterboxTTSInputWidgetIds.TTS_EXAGGERATION_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    try:
                        params.exaggeration = float(message.new_value)
                    except ValueError:
                        self.log(f"Invalid exaggeration value: {message.new_value}")
                        self.notify(
                            "Exaggeration must be a number between 0.0 and 2.0."
                        )
                        return
            case ChatterboxTTSInputWidgetIds.TTS_CFG_WEIGHT_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    try:
                        params.cfg_weight = float(message.new_value)
                    except ValueError:
                        self.log(f"Invalid pace value: {message.new_value}")
                        self.notify("Pace must be a number between 0.0 and 1.0.")
                        return
            case ChatterboxTTSInputWidgetIds.TTS_DEVICE_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    params.device = message.new_value
            case ChatterboxTTSInputWidgetIds.TTS_NANO_INPUT:
                if isinstance(params, ChatterboxParamsModel):
                    params.nano = message.new_value
            case TTSInputWidgetIds.SHIP_EFFECT_INPUT:
                self.tts_model.ship_effect = message.new_value

        self.post_message(
            SectionSettingsChanged(
                SettingsSection.TTS,
                new_value=self.tts_model,
            )
        )

    def switch_to_engine_with_remembered_or_default_params(
        self, engine: TtsEngine
    ) -> None:
        """Makes engine the one on the screen. Takes the params this engine had
        on this screen, or its defaults the first time, and writes the engine
        and those params into tts_model. The defaults of an engine seen for the
        first time are remembered too. Setting self.params recomposes the
        section, so the location select, the engine select and the settings
        of the engine are built again. The params of the engine left behind stay
        remembered, with the pilot's unsaved edits. Saves nothing, posts no
        message (on_value_changed() posts it) and leaves saved_engine as it was,
        so is_modified() sees the switch. The callers never ask for the engine
        that is already on the screen."""
        if engine not in self.params_of_every_engine:
            self.params_of_every_engine[engine] = build_default_params_for_engine(
                engine
            )
        new_params = self.params_of_every_engine[engine]
        self.tts_model.provider = engine
        self.tts_model.params = new_params
        self.params = new_params

    def is_modified(self) -> bool:
        """True when the engine differs from the saved one, or any input row of
        this section (also the rows of the Edge, Chatterbox and Pocket TTS
        blocks and the ship effect switch) differs from its saved value. The
        settings screen uses it for the section and header markers. The engine
        is compared here, because every engine switch builds the rows again
        with the new engine as their saved value, so the rows alone never show
        the switch."""
        return self.tts_model.provider != self.saved_engine or super().is_modified()

    def hide_error_and_mark_values_as_saved(self) -> None:
        """Called by the settings screen after a successful save.
        1. Does what the base container does: hides the error box and clears
           its message, and marks the value of every input row as saved (the
           "changed" mark goes away).
        2. Makes the engine on the screen the saved engine, so is_modified()
           turns False.
        Writes nothing to disk, the save already happened."""
        super().hide_error_and_mark_values_as_saved()
        self.saved_engine = self.tts_model.provider

    def compose_chatterbox_settings(
        self, chatterbox_params: ChatterboxParamsModel
    ) -> ComposeResult:
        """Part of compose(). Gives one widget, WidgetChatterboxTTSSettingsVertical,
        built from chatterbox_params: the voice profiles block, then
        exaggeration, pace, device and the Nano model switch. The block shows
        the values of chatterbox_params and its changes reach them through this
        container's on_value_changed(). Changes nothing itself."""
        yield WidgetChatterboxTTSSettingsVertical(chatterbox_params)

    def compose_pocket_settings(
        self, pocket_params: PocketParamsModel
    ) -> ComposeResult:
        """Part of compose(). Gives one widget, WidgetVoiceProfilesVertical,
        built from pocket_params: the voice select (blank when pocket_params
        has no profile, or one that is not in the list), a row with play and
        delete buttons for each cloned profile (or a hint when there is none)
        and the clone button. Pocket TTS has no other settings. A picked voice
        reaches pocket_params through this container's on_value_changed().
        Changes nothing itself."""
        yield WidgetVoiceProfilesVertical(pocket_params)

    def compose_edge_tts_settings(self, edge_params: EdgeParamsModel) -> ComposeResult:
        """Part of compose(). Gives one widget, WidgetEdgeTTSSettingsVertical,
        built from edge_params: the voice select showing edge_params.voice. The
        block asks the network for the list of voices after it is mounted and
        shows a loading indicator until the list is there. A picked voice
        reaches edge_params through this container's on_value_changed().
        Changes nothing itself."""
        yield WidgetEdgeTTSSettingsVertical(edge_params)
