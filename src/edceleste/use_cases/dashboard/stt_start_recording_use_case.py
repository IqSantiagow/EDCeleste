from edceleste.protocols.stt_protocol import SttProtocol


class SttStartRecordingUseCase:
    def __init__(self, stt_protocol: SttProtocol) -> None:
        self.stt_protocol = stt_protocol

    def __call__(self) -> None:
        """Opens the microphone and returns at once, the sound is collected
        until SttStopRecordingUseCase. Raises SttException when STT is
        disabled or a recording is already running."""
        self.stt_protocol.start_recording()
