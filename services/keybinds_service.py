import asyncio
import glob
import logging
import os

from services.models.keybinds_model import REQUIRED_KEYBINDS, Keybind
from lxml import etree  # type: ignore

logger = logging.getLogger(__name__)


class KeybindService:
    def __init__(self, keybinds_path: str):
        self.keybinds_path = keybinds_path
        self.keybinds: list[Keybind] = []

    async def load_keybinds(self):
        found_binds_files = glob.glob(self.keybinds_path + "/*.binds")

        if not found_binds_files:
            logger.warning(f"No .binds files found in {self.keybinds_path}")
            raise FileNotFoundError(f"No .binds files found in {self.keybinds_path}")

        latest_file = max(found_binds_files, key=os.path.getmtime)

        deserialized_keybinds = etree.parse(latest_file)

        root = deserialized_keybinds.getroot()

        def map_keybinds_to_model_and_load():
            self.keybinds.clear()
            for child in root:
                if child.tag in REQUIRED_KEYBINDS:
                    key = child[0].get("Key").removeprefix("Key_")
                    keybind = Keybind(key=key, action=child.tag)
                    self.keybinds.append(keybind)

        await asyncio.to_thread(map_keybinds_to_model_and_load)

        logger.info(f"Loaded {len(self.keybinds)} keybinds from {self.keybinds_path}")

    def get_keybinds(self) -> list[Keybind]:
        return self.keybinds.copy()
