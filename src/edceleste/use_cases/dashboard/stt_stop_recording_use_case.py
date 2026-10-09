from edceleste.protocols.stt_protocol import SttProtocol


class SttStopRecordingUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> str | None:
        """Stops the microphone and transcribes the recording with Whisper.
        Blocking and slow (the first call also loads the model), so run it in
        a thread. None when nothing was recorded or nothing was heard. Raises
        SttException when no recording is running."""
        return self.stt_protocol.stop_recording_and_transcribe()
