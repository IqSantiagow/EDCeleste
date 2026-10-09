from typing import Literal, Protocol


class DeviceDetectionProtocol(Protocol):
    def get_available_device(self) -> Literal["cuda", "cpu"]:
        """Tells the settings screen if a GPU can run the local voice model.
        "cuda" when torch sees a CUDA GPU, otherwise "cpu". Loads no model.
        The TTS service answers "cpu" when the active TTS provider is not
        chatterbox, even on a machine with a GPU."""
        ...
