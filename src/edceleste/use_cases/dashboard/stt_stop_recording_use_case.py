from edceleste.protocols.stt_protocol import SttProtocol


class SttStopRecordingUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> None:
        """Stops the microphone and transcribes the recording with Whisper.
        Blocking and slow (the first call also loads the model), so run it in
        a thread. Returns nothing, the text comes out of
        StreamSttTranscriptionsUseCase. Raises SttException when no recording
        is running."""
        self.stt_protocol.stop_recording_and_transcribe()
