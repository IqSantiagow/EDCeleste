from typing import Literal, Protocol

from edceleste.services.models.settings_model import TtsProviderParams


class DeviceDetectionProtocol(Protocol):
    def get_available_device(self, params: TtsProviderParams) -> Literal["cuda", "cpu"]:
        """Tells the settings screen if a GPU can run the local voice model.
        "cuda" when torch sees a CUDA GPU, otherwise "cpu". Loads no model.
        params are the TTS settings as they are on the screen now. The TTS
        service answers "cpu" when their provider is not chatterbox, even on a
        machine with a GPU."""
        ...
