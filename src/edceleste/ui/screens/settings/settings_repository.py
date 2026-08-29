from edceleste.services.models.keybinds_model import Keybind
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.use_cases.settings.exceptions.settings_validation_exception import (
    SettingsValidationException,
)
from edceleste.use_cases.settings.get_settings_use_case import GetSettingsUseCase
from edceleste.use_cases.settings.get_stt_models_use_case import GetSttModelsUseCase
from edceleste.use_cases.settings.get_stt_input_devices_use_case import (
    GetSttInputDevicesUseCase,
)
from edceleste.use_cases.settings.get_tts_voices_use_case import GetTTSVoicesUseCase
from edceleste.use_cases.settings.settings_get_keybinds_use_case import (
    SettingsGetKeybindsUseCase,
)
from edceleste.use_cases.settings.settings_load_keybinds_use_case import (
    SettingsLoadKeybindsUseCase,
)
from edceleste.use_cases.settings.update_settings_use_case import UpdateSettingsUseCase


class SettingsRepository:
    def __init__(
        self,
        settings_load_keybinds_use_case: SettingsLoadKeybindsUseCase,
        settings_get_keybinds_use_case: SettingsGetKeybindsUseCase,
        update_settings_use_case: UpdateSettingsUseCase,
        get_settings_use_case: GetSettingsUseCase,
        get_tts_voices_use_case: GetTTSVoicesUseCase,
        get_stt_models_use_case: GetSttModelsUseCase,
        get_stt_input_devices_use_case: GetSttInputDevicesUseCase,
    ) -> None:
        self.settings_load_keybinds_use_case = settings_load_keybinds_use_case
        self.settings_get_keybinds_use_case = settings_get_keybinds_use_case
        self.update_settings_use_case = update_settings_use_case
        self.get_settings_use_case = get_settings_use_case
        self.get_tts_voices_use_case = get_tts_voices_use_case
        self.get_stt_models_use_case = get_stt_models_use_case
        self.get_stt_input_devices_use_case = get_stt_input_devices_use_case

    def get_keybinds(self) -> list[Keybind]:
        return self.settings_get_keybinds_use_case()

    def load_keybinds(self) -> None:
        self.settings_load_keybinds_use_case()

    def update_settings(self, new_settings: SettingsModel) -> list[SettingsIssueModel]:
        try:
            self.update_settings_use_case(new_settings)
            return []
        except SettingsValidationException as e:
            return e.issues

    def get_settings(self) -> SettingsModel:
        return self.get_settings_use_case()

    async def get_voices(self) -> list[str]:
        return await self.get_tts_voices_use_case()

    def get_stt_models(self) -> list[str]:
        return self.get_stt_models_use_case()

    def get_stt_input_devices(self) -> list[tuple[str, int]]:
        return self.get_stt_input_devices_use_case()
