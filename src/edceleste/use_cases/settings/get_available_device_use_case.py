from typing import Literal

from edceleste.protocols.device_detection_protocol import DeviceDetectionProtocol


class GetAvailableDeviceUseCase:
    def __init__(self, device_detection_protocol: DeviceDetectionProtocol):
        self.device_detection_protocol = device_detection_protocol

    def __call__(self) -> Literal["cuda", "cpu"]:
        """Asks torch, through the TTS service, if a CUDA GPU is there. Loads
        no model. Says "cpu" when the active TTS provider is not chatterbox,
        even with a GPU."""
        return self.device_detection_protocol.get_available_device()
