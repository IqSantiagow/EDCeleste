from services.models.keybinds_model import Keybind
from use_cases.settings.settings_get_keybinds_use_case import SettingsGetKeybindsUseCase
from use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)


class SettingsRepository:
    def __init__(
        self,
        settings_load_keybinds_use_case: SettingsLoadKeybindsUseCase,
        settings_get_keybinds_use_case: SettingsGetKeybindsUseCase,
    ) -> None:
        self.settings_load_keybinds_use_case = settings_load_keybinds_use_case
        self.settings_get_keybinds_use_case = settings_get_keybinds_use_case

    def get_keybinds(self) -> list[Keybind]:
        return self.settings_get_keybinds_use_case()

    async def load_keybinds(self) -> None:
        await self.settings_load_keybinds_use_case()
