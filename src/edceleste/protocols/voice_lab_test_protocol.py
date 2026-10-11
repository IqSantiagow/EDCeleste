from typing import Protocol

from edceleste.services.models.settings_model import TTSModel


class VoiceLabTestProtocol(Protocol):
    async def play_voice_lab_test_sentence(self, tts_settings: TTSModel) -> None:
        """Lets the pilot hear the Voice Lab. Speaks one fixed sentence with the
        engine, the volume and the Voice Lab switch and sliders from
        tts_settings, plays it and waits until it ends. tts_settings are the
        TTS settings as they are on the screen now, saved or not. Nothing is
        saved. Raises ValueError when the engine on the screen is not set up
        (no voice, no profile) and passes on the errors of the engine (no
        network, a missing profile file)."""
        ...
