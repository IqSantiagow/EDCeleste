from services.models.keybinds_model import Keybind
from services.models.settings_model import (
    SettingsModel,
    PathModel,
    PromptModel,
    TTSModel,
)
from use_cases.settings.get_settings_use_case import GetSettingsUseCase
from use_cases.settings.load_settings_use_case import LoadSettingsUseCase
from use_cases.settings.settings_get_keybinds_use_case import SettingsGetKeybindsUseCase
from use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)
from use_cases.settings.update_settings_use_case import UpdateSettingsUseCase


class SettingsRepository:
    def __init__(
        self,
        settings_load_keybinds_use_case: SettingsLoadKeybindsUseCase,
        settings_get_keybinds_use_case: SettingsGetKeybindsUseCase,
        load_settings_use_case: LoadSettingsUseCase,
        update_settings_use_case: UpdateSettingsUseCase,
        get_settings_use_case: GetSettingsUseCase,
    ) -> None:
        self.settings_load_keybinds_use_case = settings_load_keybinds_use_case
        self.settings_get_keybinds_use_case = settings_get_keybinds_use_case
        self.load_settings_use_case = load_settings_use_case
        self.update_settings_use_case = update_settings_use_case
        self.get_settings_use_case = get_settings_use_case

    def get_keybinds(self) -> list[Keybind]:
        return self.settings_get_keybinds_use_case()

    async def load_keybinds(self) -> None:
        await self.settings_load_keybinds_use_case()

    def load_settings(self) -> None:
        self.load_settings_use_case()

    def update_settings(self, new_settings: SettingsModel) -> None:
        self.update_settings_use_case(new_settings)

    def update_paths(self, new_paths: PathModel) -> None:
        current_settings = self.get_settings_use_case()
        current_settings.paths = new_paths
        self.update_settings(current_settings)

    def update_prompts(self, new_prompts: PromptModel) -> None:
        current_settings = self.get_settings_use_case()
        current_settings.prompts = new_prompts
        self.update_settings(current_settings)

    def update_tts(self, new_tts: TTSModel) -> None:
        current_settings = self.get_settings_use_case()
        current_settings.tts = new_tts
        self.update_settings(current_settings)

    def get_path_settings(self) -> PathModel:
        return self.get_settings_use_case().paths

    def get_prompt_settings(self) -> PromptModel:
        return self.get_settings_use_case().prompts

    def get_tts_settings(self) -> TTSModel:
        return self.get_settings_use_case().tts
