from typing import Protocol

from services.models.keybinds_model import EdAction, Keybind
from services.models.settings_model import SettingsIssueModel, SettingsModel


class KeybindsProtocol(Protocol):
    def load_keybinds(self) -> None: ...

    def get_keybinds(self) -> list[Keybind]: ...

    def resolve(self, action: EdAction) -> Keybind: ...

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...
