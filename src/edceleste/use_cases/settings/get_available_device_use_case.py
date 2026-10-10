from typing import Literal

from edceleste.protocols.device_detection_protocol import DeviceDetectionProtocol
from edceleste.services.models.settings_model import TtsProviderParams


class GetAvailableDeviceUseCase:
    def __init__(self, device_detection_protocol: DeviceDetectionProtocol):
        self.device_detection_protocol = device_detection_protocol

    def __call__(self, params: TtsProviderParams) -> Literal["cuda", "cpu"]:
        """Asks torch, through the TTS service, if a CUDA GPU is there. Loads
        no model. params are the TTS settings as they are on the screen now.
        Says "cpu" when their provider is not chatterbox, even with a GPU."""
        return self.device_detection_protocol.get_available_device(params)
