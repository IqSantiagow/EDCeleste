from protocols.stt_protocol import SttProtocol


class GetSttInputDevicesUseCase:
    def __init__(self, stt_protocol: SttProtocol):
        self.stt_protocol = stt_protocol

    def __call__(self) -> list[tuple[str, int]]:
        return self.stt_protocol.get_stt_input_devices()
