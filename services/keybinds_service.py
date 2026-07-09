import asyncio
import glob
import logging
import os
import pydirectinput

from services.event_bus import EventBus
from services.models.keybinds_model import EdAction, Keybind, MissingKeybindsError
from lxml import etree  # type: ignore

logger = logging.getLogger(__name__)


class KeybindService:
    def __init__(self, keybinds_path: str, event_bus: EventBus) -> None:
        self.keybinds_path = keybinds_path
        self._keybinds_by_action: dict[EdAction, Keybind] = {}
        self._event_bus = event_bus
        self._event_bus.subscribe(EdAction, self.perform_action)

    async def load_keybinds(self):
        found_binds_files = glob.glob(self.keybinds_path + "/*.binds")

        if not found_binds_files:
            logger.warning(f"No .binds files found in {self.keybinds_path}")
            raise FileNotFoundError(f"No .binds files found in {self.keybinds_path}")

        latest_file = max(found_binds_files, key=os.path.getmtime)

        root = etree.parse(latest_file).getroot()

        def parse_keybinds() -> dict[EdAction, Keybind]:
            loaded: dict[EdAction, Keybind] = {}
            for child in root:
                try:
                    action = EdAction(child.tag)
                except (ValueError, TypeError):
                    continue  # tag we don't map (or an XML comment) -> skip
                key = child[0].get("Key").removeprefix("Key_")
                loaded[action] = Keybind(key=key, action=action)
            return loaded

        loaded = await asyncio.to_thread(parse_keybinds)

        missing = set(EdAction) - loaded.keys()
        if missing:
            raise MissingKeybindsError(missing)

        self._keybinds_by_action = loaded

        logger.info(
            f"Loaded {len(self._keybinds_by_action)} keybinds from {self.keybinds_path}"
        )

    def get_keybinds(self) -> list[Keybind]:
        return list(self._keybinds_by_action.values())

    def resolve(self, action: EdAction) -> Keybind:
        return self._keybinds_by_action[action]

    def perform_action(self, action: EdAction) -> None:
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
