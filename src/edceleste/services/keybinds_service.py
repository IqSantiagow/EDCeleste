from collections.abc import AsyncGenerator
import glob
import logging
import os

from edceleste.services.event_bus import EventBus
from edceleste.services.exceptions.game_window_exception import (
    GameWindowNotFoundException,
)
from edceleste.services.game_window import GameWindow
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.settings_service import SettingsService
from edceleste.services.models.keybinds_model import (
    EdAction,
    Keybind,
    MissingKeybindsError,
    action_in_plain_words,
)
from lxml import etree  # type: ignore

from edceleste.services.models.settings_model import (
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
            """Lets the module import outside Windows. Pressing a key still fails."""
            raise RuntimeError("pydirectinput is only available on Windows")

        @staticmethod
        def keyDown(key: str) -> None:
            """Lets the module import outside Windows. Holding a key still fails."""
            raise RuntimeError("pydirectinput is only available on Windows")

        @staticmethod
        def keyUp(key: str) -> None:
            """Lets the module import outside Windows. Letting go still fails."""
            raise RuntimeError("pydirectinput is only available on Windows")

    pydirectinput = _PydirectinputStub()  # type: ignore[assignment]


class KeybindService:
    def __init__(
        self,
        keybinds_path: str,
        event_bus: EventBus,
        settings_service: SettingsService,
        game_window: GameWindow,
        key_presser=None,
    ) -> None:
        """Only stores the dependencies and subscribes to the event bus. The
        .binds file is not read here, that happens in reload_service().

        key_presser is pydirectinput by default, tests pass a fake, so no real
        key is pressed.

        Subscriptions:
        - EdAction -> press_keys_for_action
        """
        self.__settings_service = settings_service
        self.keybinds_path = keybinds_path
        self.game_window = game_window
        # used for tests
        self.key_presser = key_presser or pydirectinput
        self._keybinds_by_action: dict[EdAction, Keybind] = {}
        self._event_bus = event_bus
        self._event_bus.subscribe(EdAction, self.press_keys_for_action)

    def load_keybinds(self):
        """Reads the game's keybinds from disk.

        1. Finds every .binds file in keybinds_path, raises FileNotFoundError
           when there is none.
        2. Takes the newest file, the one the game wrote last.
        3. Parses it and raises MissingKeybindsError when an action we use is
           not in the file.
        4. Only then replaces the loaded keybinds, so a failed load keeps the
           old ones.
        """
        found_binds_files = self._get_bind_files_or_throw_if_none(self.keybinds_path)

        latest_file = max(found_binds_files, key=os.path.getmtime)

        loaded = self._parse_keybinds(latest_file)

        self._validate_missing_keybinds(loaded)

        self._keybinds_by_action = loaded

        logger.info(
            f"Loaded {len(self._keybinds_by_action)} keybinds from {self.keybinds_path}"
        )

    def get_keybinds(self) -> list[Keybind]:
        """A copy of the loaded keybinds, unbound actions included (key None).
        Empty before load_keybinds() ran."""
        return list(self._keybinds_by_action.values())

    def find_keybind_for_action(self, action: EdAction) -> Keybind:
        """Looks the action up in the loaded keybinds, nothing is read from
        disk. Raises KeyError when the keybinds are not loaded yet."""
        return self._keybinds_by_action[action]

    def is_bound(self, action: EdAction) -> bool:
        """False when the action has no keyboard key, e.g. it is bound only
        to a joystick. Raises KeyError when the keybinds are not loaded yet."""
        return self.find_keybind_for_action(action).key is not None

    async def press_keys_for_action(self, action: EdAction) -> None:
        """Presses the action's keys in the game. Runs when an EdAction is
        published on the event bus and when the PerformGameAction tool calls it.

        1. No keyboard key -> logs a warning and presses nothing.
        2. Brings the game window to the front, otherwise the key would be
           typed into our terminal. Raises GameWindowNotFoundException when
           the game is not running.
        3. Holds the modifiers down, presses the key, then lets the modifiers
           go in reverse order. The modifiers are let go even when the press
           fails, the error is raised after that.
        """
        keybind = self.find_keybind_for_action(action)
        if keybind.key is None:
            logger.warning(
                f"Action '{action.value}' has no keyboard key, nothing is pressed"
            )
            return

        # A key pressed while the terminal has focus would be typed into the terminal
        if not await self.game_window.bring_to_front():
            raise GameWindowNotFoundException(
                f"Game window not found, '{action.value}' is not pressed"
            )

        normalized_key = self._normalize_key(keybind.key)
        normalized_modifiers = [self._normalize_key(m) for m in keybind.modifiers]

        for modifier in normalized_modifiers:
            self.key_presser.keyDown(modifier)
        try:
            self.key_presser.press(normalized_key)
        finally:
            # Always let go of the modifiers, a stuck Shift breaks the game controls
            for modifier in reversed(normalized_modifiers):
                self.key_presser.keyUp(modifier)

        logger.info(
            f"Performing action '{action.value}' bound to key "
            f"'{'+'.join([*normalized_modifiers, normalized_key])}'"
        )

    def _normalize_key(self, key: str) -> str:
        """Translates a key name from the .binds file (without "Key_") into the
        name pydirectinput understands, e.g. "UpArrow" -> "up",
        "LeftShift" -> "shiftleft", "Comma" -> ",". Any other key is just
        lowercased. The first matching rule wins, so the order matters:
        "BackSlash" must be checked before "Slash"."""
        if "Arrow" in key:
            return key.replace("Arrow", "").lower()
        if "LeftShift" in key:
            return "shiftleft"
        if "RightShift" in key:
            return "shiftright"
        if "LeftControl" in key:
            return "ctrlleft"
        if "RightControl" in key:
            return "ctrlright"
        if "LeftAlt" in key:
            return "altleft"
        if "RightAlt" in key:
            return "altright"
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
    ) -> SettingsIssueModel | None:
        """Checks the keybindings path of new settings before they are saved.
        Reads the disk.

        Checks in order and returns the first issue:
        1. the path is set,
        2. the folder has at least one .binds file,
        3. that file has every action we use.
        Returns None when everything is fine. Other errors, e.g. a broken XML
        file, are not caught and are raised.
        """
        if not new_settings.paths.keybindings_path:
            return SettingsIssueModel(
                section="paths",
                field="keybindings_path",
                message="Keybindings path is not set.",
            )

        try:
            self._get_bind_files_or_throw_if_none(new_settings.paths.keybindings_path)
        except FileNotFoundError as e:
            return SettingsIssueModel(
                section="paths",
                field="keybindings_path",
                message=str(e),
            )

        try:
            self._validate_missing_keybinds(
                self._parse_keybinds(
                    self._get_bind_files_or_throw_if_none(
                        new_settings.paths.keybindings_path
                    )[0]
                )
            )
        except MissingKeybindsError as e:
            return SettingsIssueModel(
                section="paths",
                field="keybindings_path",
                message=str(e),
            )
        return None

    def _get_bind_files_or_throw_if_none(self, path: str) -> list[str]:
        """Only looks directly in path, not in subfolders. The files come in
        no particular order."""
        found_binds_files = glob.glob(path + "/*.binds")

        if not found_binds_files:
            logger.warning(f"No .binds files found in {path}")
            raise FileNotFoundError(f"No .binds files found in {path}")

        return found_binds_files

    def _parse_keybinds(self, file) -> dict[EdAction, Keybind]:
        """Reads the .binds XML file. Keeps only the actions listed in
        EdAction, every other tag and XML comment is skipped. An action
        without a keyboard binding is still kept, with key None."""
        tree = etree.parse(file)
        root = tree.getroot()
        loaded: dict[EdAction, Keybind] = {}
        for child in root:
            try:
                action = EdAction(child.tag)
            except (ValueError, TypeError):
                continue  # tag we don't map (or an XML comment) -> skip
            loaded[action] = self._read_keyboard_keybind(action, child)
        return loaded

    def _read_keyboard_keybind(self, action: EdAction, action_element) -> Keybind:
        """The primary binding if it is on the keyboard, otherwise the
        secondary one. A binding with a joystick modifier is skipped too. With
        no keyboard binding at all the action is unbound (key None). The
        "Key_" prefix is cut from every key name."""
        primary = action_element.find("Primary")
        secondary = action_element.find("Secondary")
        for binding in (primary, secondary):
            if binding is None or binding.get("Device") != "Keyboard":
                continue
            modifiers = binding.findall("Modifier")
            # A modifier on a joystick can't be pressed from the keyboard
            if any(modifier.get("Device") != "Keyboard" for modifier in modifiers):
                continue
            return Keybind(
                action=action,
                key=binding.get("Key").removeprefix("Key_"),
                modifiers=[
                    modifier.get("Key").removeprefix("Key_") for modifier in modifiers
                ],
            )
        return Keybind(action=action, key=None)

    def _validate_missing_keybinds(self, loaded: dict[EdAction, Keybind]) -> None:
        """Raises MissingKeybindsError with every EdAction that is not in the
        file at all. An action that is in the file but has no keyboard key is
        not missing."""
        missing = set(EdAction) - loaded.keys()
        if missing:
            raise MissingKeybindsError(missing)

    def reload_service(self):
        """Reads the keybinds again from the path in the saved settings.
        Called by cold_start() and after the settings change.
        The old keybinds are dropped first, so when loading fails no action is
        known any more. Errors from load_keybinds() are raised."""
        new_settings = self.__settings_service.get_settings()
        self.keybinds_path = new_settings.paths.keybindings_path
        self._keybinds_by_action.clear()

        self.load_keybinds()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Loads the keybinds (reload_service).
        3. Yields completed. Actions without a keyboard key make it a warning
           that lists them in plain words. Never raises, a failed load ends up
           in the status message.
        """
        status = ColdStartStatus(
            service="keybinds",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status

        try:
            self.reload_service()
            unbound_actions = [
                keybind.action
                for keybind in self._keybinds_by_action.values()
                if keybind.key is None
            ]
            if unbound_actions:
                unbound_names = [action_in_plain_words(a) for a in unbound_actions]
                logger.warning(f"Actions without a keyboard key: {unbound_names}")
                status.is_warning = True
                status.message = f"No keyboard key for: {', '.join(unbound_names)}"
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
