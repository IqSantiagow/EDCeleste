from typing import Protocol

from edceleste.services.models.settings_model import TTSModel


class VoiceTestProtocol(Protocol):
    async def play_voice_test_sentence(self, tts_settings: TTSModel) -> None:
        """Lets the pilot hear the voice. Implemented by TTSService. Speaks one
        fixed sentence with the engine, the volume and the ship effect switch
        from tts_settings, plays it and returns when the sound ends, which can
        take seconds (Chatterbox and Pocket TTS load their voice model, Edge
        goes to the network). tts_settings are the TTS settings as they are
        on the screen now, saved or not. Nothing is saved. Raises ValueError
        when the engine on the screen is not set up (no voice, no profile) and
        passes on the errors of the engine (no network, a missing profile
        file)."""
        ...
