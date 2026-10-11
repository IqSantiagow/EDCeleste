from edceleste.protocols.voice_lab_test_protocol import VoiceLabTestProtocol
from edceleste.services.models.settings_model import TTSModel


class PlayVoiceLabTestUseCase:
    def __init__(self, voice_lab_test_protocol: VoiceLabTestProtocol):
        self.voice_lab_test_protocol = voice_lab_test_protocol

    async def __call__(self, tts_settings: TTSModel) -> None:
        """Slow for Chatterbox (loads the voice model on first use), goes to the
        network for Edge. Speaks the Voice Lab test sentence with the TTS
        settings as they are on the screen now, with their Voice Lab effects,
        plays it and returns when the sound ends. Nothing is saved. Raises
        ValueError when the engine on the screen is not set up and passes on
        the errors of the engine."""
        await self.voice_lab_test_protocol.play_voice_lab_test_sentence(tts_settings)
