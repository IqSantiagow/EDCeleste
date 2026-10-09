from typing import Protocol

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.keybinds_model import EdAction, Keybind
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class KeybindsProtocol(BaseServiceProtocol, Protocol):
    def load_keybinds(self) -> None:
        """Reads the newest .binds file from the keybindings path the service
        holds now (the saved settings, not the ones being edited) and fills
        the keybinds cache. Raises FileNotFoundError when there is no .binds
        file and MissingKeybindsError when an action we need is not in the
        file. On error the old cache stays as it was."""
        ...

    def get_keybinds(self) -> list[Keybind]:
        """Only reads the cache, never the disk. Empty until load_keybinds()
        or reload_service() worked. An action without a keyboard key is still
        in the list, with key=None."""
        ...

    def find_keybind_for_action(self, action: EdAction) -> Keybind:
        """Looks the action up in the cache. Raises KeyError when the keybinds
        are not loaded yet. key=None means the action has no keyboard key."""
        ...

    def is_bound(self, action: EdAction) -> bool:
        """True when the action can be pressed from the keyboard. Raises
        KeyError, like find_keybind_for_action(), when the keybinds are not
        loaded yet."""
        ...

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Reads the .binds files from the keybindings path of settings that
        are not saved yet and checks that every action we need is there.
        Changes nothing in the service, the cache stays as it was. None means
        fine."""
        ...

    def reload_service(self) -> None:
        """Takes the keybindings path from the saved settings, empties the
        cache and loads it again with load_keybinds(). Raises like
        load_keybinds(), and then the cache stays empty."""
        ...
