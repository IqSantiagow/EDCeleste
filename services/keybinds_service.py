import glob
import logging
import os

from services.event_bus import EventBus
from services.settings_service import SettingsService
from services.models.keybinds_model import EdAction, Keybind, MissingKeybindsError
from lxml import etree  # type: ignore

from services.models.settings_model import (
    SettingsIssueModel,
    SettingsModel,
)  # type: ignore

logger = logging.getLogger(__name__)

try:
    import pydirectinput
except ImportError:  # pydirectinput needs ctypes.WinDLL, so it only imports on Windows

    class _PydirectinputStub:
        @staticmethod
        def press(key: str) -> None:
            raise RuntimeError("pydirectinput is only available on Windows")

    pydirectinput = _PydirectinputStub()  # type: ignore[assignment]


class KeybindService:
    def __init__(
        self, keybinds_path: str, event_bus: EventBus, settings_handler: SettingsService
    ) -> None:
        self.__settings_handler = settings_handler
        self.keybinds_path = keybinds_path
        self._keybinds_by_action: dict[EdAction, Keybind] = {}
        self._event_bus = event_bus
        self._event_bus.subscribe(EdAction, self.perform_action)

        self.reload_service()

    def load_keybinds(self):
        found_binds_files = self._get_bind_files_or_throw_if_none(self.keybinds_path)

        latest_file = max(found_binds_files, key=os.path.getmtime)

        loaded = self._parse_keybinds(latest_file)

        self._validate_missing_keybinds(loaded)

        self._keybinds_by_action = loaded

        logger.info(
            f"Loaded {len(self._keybinds_by_action)} keybinds from {self.keybinds_path}"
        )

    def get_keybinds(self) -> list[Keybind]:
        return list(self._keybinds_by_action.values())

    def resolve(self, action: EdAction) -> Keybind:
        return self._keybinds_by_action[action]

    async def perform_action(self, action: EdAction) -> None:
        keybind = self.resolve(action)
        normalized_key = self._normalize_key(keybind.key)
        pydirectinput.press(normalized_key)
        logger.info(
            f"Performing action '{action.value}' bound to key '{normalized_key}'"
        )

    def _normalize_key(self, key: str) -> str:
        if "Arrow" in key:
            return key.replace("Arrow", "").lower()
        if "LeftShift" in key:
            return "shiftleft"
        if "LeftControl" in key:
            return "ctrlleft"
        if "Apostrophe" in key:
            return "'"
        if "BackSlash" in key:
            return "\\"
        if "Comma" in key:
            return ","
        if "Period" in key:
            return "."
        if "Slash" in key:
            return "/"

        return key.lower()

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> list[SettingsIssueModel]:
        issues = []
        if not new_settings.paths.keybindings_path:
            issues.append(
                SettingsIssueModel(
                    section=str(self.__class__),
                    field="keybindings_path",
                    message="Keybindings path is not set.",
                )
            )
            return issues

        try:
            self._get_bind_files_or_throw_if_none(new_settings.paths.keybindings_path)
        except FileNotFoundError as e:
            issues.append(
                SettingsIssueModel(
                    section=str(self.__class__),
                    field="keybindings_path",
                    message=str(e),
                )
            )
            return issues

        try:
            self._validate_missing_keybinds(
                self._parse_keybinds(
                    self._get_bind_files_or_throw_if_none(
                        new_settings.paths.keybindings_path
                    )[0]
                )
            )
        except MissingKeybindsError as e:
            issues.append(
                SettingsIssueModel(
                    section=str(self.__class__),
                    field="keybindings_path",
                    message=str(e),
                )
            )
        return issues

    def _get_bind_files_or_throw_if_none(self, path: str) -> list[str]:
        found_binds_files = glob.glob(path + "/*.binds")

        if not found_binds_files:
            logger.warning(f"No .binds files found in {path}")
            raise FileNotFoundError(f"No .binds files found in {path}")

        return found_binds_files

    def _parse_keybinds(self, file) -> dict[EdAction, Keybind]:
        tree = etree.parse(file)
        root = tree.getroot()
        loaded: dict[EdAction, Keybind] = {}
        for child in root:
            try:
                action = EdAction(child.tag)
            except (ValueError, TypeError):
                continue  # tag we don't map (or an XML comment) -> skip
            key = child[0].get("Key").removeprefix("Key_")
            loaded[action] = Keybind(key=key, action=action)
        return loaded

    def _validate_missing_keybinds(self, loaded: dict[EdAction, Keybind]) -> None:
        missing = set(EdAction) - loaded.keys()
        if missing:
            raise MissingKeybindsError(missing)

    def reload_service(self):
        new_settings = self.__settings_handler.get_settings()
        self.keybinds_path = new_settings.paths.keybindings_path
        self._keybinds_by_action.clear()

        self.load_keybinds()
