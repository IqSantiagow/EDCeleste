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
        """Says a short reply of a fast command out loud and returns when it has
        played. When the voice of the saved settings has a prepared clip of
        this text (see REPLY_TEXTS) the clip is played, which starts at once.
        Otherwise the text is spoken live, which is slower. Raises what the
        provider raises."""
        ...

    async def fetch_edge_tts_voice_names(self) -> list[str]:
        """Downloads the edge-tts voice list over the network and returns the
        voice short names, e.g. "en-US-AriaNeural". Works for any active
        provider. Raises when the network call fails."""
        ...
