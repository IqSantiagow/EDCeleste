from edceleste.protocols.voice_test_protocol import VoiceTestProtocol
from edceleste.services.models.settings_model import TTSModel


class PlayVoiceTestUseCase:
    def __init__(self, voice_test_protocol: VoiceTestProtocol):
        self.voice_test_protocol = voice_test_protocol

    async def __call__(self, tts_settings: TTSModel) -> None:
        """Plays the voice test sentence. Hands tts_settings, the TTS settings
        as they are on the screen now (saved or not), to the TTS service, which
        speaks the sentence with their engine and volume, adds the ship effect
        when it is on and plays it. Returns when the sound ends. Nothing is
        saved. Slow for Chatterbox and Pocket TTS (load the voice model), goes
        to the network for Edge. Raises ValueError when the engine on the screen
        is not set up and passes on the errors of the engine. Catches nothing:
        the caller (the Test voice button) shows the error to the pilot."""
        await self.voice_test_protocol.play_voice_test_sentence(tts_settings)
