import asyncio
import logging
import os

import edge_tts
import sounddevice as sd
import soundfile as sf

from services.event_bus import EventBus

logger = logging.getLogger(__name__)


class TTSEvent:
    def __init__(self, text: str):
        self.text = text


class TTSService:
    def __init__(self, voice, event_bus: EventBus) -> None:
        self.voice = voice  # TODO: Make this configurable in the future
        self.__event_bus = event_bus
        self.__event_bus.subscribe(TTSEvent, self.handle_tts_request)

    async def synthesize(self, text):
        audio_output = edge_tts.Communicate(text, voice=self.voice)
        logger.info("Synthesizing TTS for text: %s", text)

        await audio_output.save("output.mp3")

        data, samplerate = sf.read("output.mp3")

        sd.play(data, samplerate)

        await asyncio.sleep(len(data) / samplerate)

        os.remove("output.mp3")

    async def handle_tts_request(self, event: TTSEvent):
        logger.info("Received TTS request: %s", event.text)
        await self.synthesize(event.text)
