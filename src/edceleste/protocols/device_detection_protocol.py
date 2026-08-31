from typing import Literal, Protocol


class DeviceDetectionProtocol(Protocol):
    def get_available_device(self) -> Literal["cuda", "cpu"]: ...
