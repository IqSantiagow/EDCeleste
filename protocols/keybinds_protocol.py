from typing import Protocol

from services.models.keybinds_model import Keybind


class KeybindsProtocol(Protocol):
    async def load_keybinds(self) -> None: ...

    def get_keybinds(self) -> list[Keybind]: ...
