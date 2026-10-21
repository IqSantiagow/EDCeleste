from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class TTSProtocol(BaseServiceProtocol, Protocol):
    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Asks a new provider of the chosen type (edge, chatterbox or pocket)
        to check the tts part of settings that are not saved yet: edge needs a
        voice, chatterbox and pocket a profile. Loads no voice model and
        changes nothing in the service. None means fine."""
        ...

    def reload_service(self) -> None:
        """Reads the tts part of the saved settings. A new provider type builds
        a new provider. The same type changes nothing, the provider gets the
        saved params with every sentence, and chatterbox loads its model again
        when the device or nano changed. No model is loaded here, that happens
        on the first speech."""
        ...

    async def speak_reply(self, text: str) -> None:
        """Says a short reply (a fast command or a change of the game state) out
        loud and returns when it has played. Does nothing when the switch
        tts.play_ship_replies is off. When the voice of the saved settings has a
        prepared clip of this text (see REPLY_TEXTS) the clip is played, which
        starts at once. Otherwise the text is spoken live, which is slower. The
        clip and the live voice use the saved volume and the ship effect (when
        it is on). Raises RuntimeError when the provider is not built yet and
        the clip is missing, ValueError for an empty profile name, the error of
        soundfile for a clip that cannot be read, and what the provider and the
        speaker raise."""
        ...

    async def fetch_edge_tts_voice_names(self) -> list[str]:
        """Downloads the edge-tts voice list over the network and returns the
        voice short names, e.g. "en-US-AriaNeural". Works for any active
        provider. Raises when the network call fails."""
        ...
