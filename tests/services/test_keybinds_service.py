import unittest
from unittest.mock import Mock, patch

from lxml import etree  # type: ignore

from services.event_bus import EventBus
from services.keybinds_service import KeybindService
from services.llm_service import SYSTEM_PROMPT
from services.models.keybinds_model import EdAction, Keybind, MissingKeybindsError
from services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from tests import TEST_BINDS_FILE_LOCATION
from services.settings_service import SettingsService

KEYBINDS_PATH = "C:/keybinds"
REQUIRED_KEYBINDS_COUNT = len(EdAction)


def _make_settings(api_key: str) -> SettingsModel:
    return SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key=api_key, system_prompt=SYSTEM_PROMPT, user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


class KeybindServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        glob_patcher = patch("services.keybinds_service.glob.glob")
        getmtime_patcher = patch("services.keybinds_service.os.path.getmtime")

        self.mock_glob = glob_patcher.start()
        self.mock_getmtime = getmtime_patcher.start()

        self.addCleanup(glob_patcher.stop)
        self.addCleanup(getmtime_patcher.stop)

        self.mock_glob.return_value = [str(TEST_BINDS_FILE_LOCATION)]
        self.mock_getmtime.return_value = 100

        self.settings_handler = Mock(spec=SettingsService)

        self.settings_handler.get_settings.return_value = _make_settings(
            api_key="sk-ant-test"
        )

    def _make_service(self):
        return KeybindService(
            keybinds_path=KEYBINDS_PATH,
            event_bus=EventBus(),
            settings_handler=self.settings_handler,
        )

    def test_should_raise_file_not_found_error_when_no_binds_files_found(self):
        self.mock_glob.return_value = []

        # KeybindService.__init__ eagerly loads keybinds via _init_service,
        # so construction itself is what raises here.
        with self.assertRaises(FileNotFoundError):
            self._make_service()

    def test_should_select_latest_binds_file_by_modification_time(self):
        self.mock_glob.return_value = [
            f"{KEYBINDS_PATH}/older.binds",
            f"{KEYBINDS_PATH}/newer.binds",
        ]
        self.mock_getmtime.side_effect = [100, 200]

        with patch("services.keybinds_service.etree.parse") as mock_parse:
            mock_parse.return_value.getroot.return_value = []

            # An empty root means every required keybind is absent, so
            # construction (which eagerly loads keybinds) fails fast; we
            # still assert the newest file was the one parsed.
            with self.assertRaises(MissingKeybindsError):
                self._make_service()

            mock_parse.assert_called_once_with(f"{KEYBINDS_PATH}/newer.binds")

    def test_should_load_only_required_keybinds_from_binds_file(self):
        service = self._make_service()

        service.load_keybinds()

        keybinds = service.get_keybinds()
        self.assertEqual(len(keybinds), REQUIRED_KEYBINDS_COUNT)

        keybinds_by_action = {kb.action: kb.key for kb in keybinds}
        self.assertEqual(keybinds_by_action["ToggleFlightAssist"], "Z")
        self.assertEqual(keybinds_by_action["UIFocus"], "LeftShift")
        self.assertEqual(keybinds_by_action["QuickCommsPanel"], "Enter")
        self.assertEqual(keybinds_by_action["ToggleCargoScoop"], "Home")
        self.assertEqual(keybinds_by_action["ExplorationFSSEnter"], "Apostrophe")
        self.assertNotIn("YawLeftButton", keybinds_by_action)

    def test_should_strip_key_prefix_from_all_loaded_keys(self):
        service = self._make_service()

        service.load_keybinds()

        for keybind in service.get_keybinds():
            self.assertFalse(keybind.key.startswith("Key_"))

    def test_should_replace_keybinds_when_load_keybinds_called_twice(self):
        service = self._make_service()

        service.load_keybinds()
        service.load_keybinds()

        self.assertEqual(len(service.get_keybinds()), REQUIRED_KEYBINDS_COUNT)

    def test_get_keybinds_returns_copy_not_internal_list(self):
        service = self._make_service()
        service.load_keybinds()

        returned = service.get_keybinds()
        returned.clear()

        self.assertEqual(len(service.get_keybinds()), REQUIRED_KEYBINDS_COUNT)

    def test_resolve_returns_keybind_for_action(self):
        service = self._make_service()
        service.load_keybinds()

        keybind = service.resolve(EdAction.TOGGLE_FLIGHT_ASSIST)

        self.assertIsInstance(keybind, Keybind)
        self.assertEqual(keybind.action, EdAction.TOGGLE_FLIGHT_ASSIST)
        self.assertEqual(keybind.key, "Z")

    def test_every_action_resolves_after_load(self):
        # Exhaustiveness guard: adding an EdAction without a binding in the
        # fixture breaks this (via fail-fast on load), catching gaps at dev time.
        service = self._make_service()
        service.load_keybinds()

        for action in EdAction:
            self.assertIsInstance(service.resolve(action), Keybind)

    def test_load_raises_missing_keybinds_error_when_action_absent(self):
        root = etree.fromstring(
            b"<Root><ToggleFlightAssist>"
            b'<Primary Device="Keyboard" Key="Key_Z" />'
            b"</ToggleFlightAssist></Root>"
        )

        with patch("services.keybinds_service.etree.parse") as mock_parse:
            mock_parse.return_value.getroot.return_value = root

            # Construction eagerly loads keybinds, so it raises here rather
            # than on a later explicit load_keybinds() call.
            with self.assertRaises(MissingKeybindsError) as ctx:
                self._make_service()

        self.assertIn(EdAction.SELECT_TARGET, ctx.exception.missing)
        self.assertNotIn(EdAction.TOGGLE_FLIGHT_ASSIST, ctx.exception.missing)

    def test_normalize_key_strips_arrow_prefix_and_lowercases_direction(self):
        service = self._make_service()

        self.assertEqual(service._normalize_key("UpArrow"), "up")
        self.assertEqual(service._normalize_key("DownArrow"), "down")
        self.assertEqual(service._normalize_key("LeftArrow"), "left")
        self.assertEqual(service._normalize_key("RightArrow"), "right")

    def test_normalize_key_maps_left_shift_and_left_control_to_modifier_names(self):
        service = self._make_service()

        self.assertEqual(service._normalize_key("LeftShift"), "shiftleft")
        self.assertEqual(service._normalize_key("LeftControl"), "ctrlleft")

    def test_normalize_key_maps_punctuation_key_names_to_literal_characters(self):
        service = self._make_service()

        self.assertEqual(service._normalize_key("Apostrophe"), "'")
        self.assertEqual(service._normalize_key("BackSlash"), "\\")
        self.assertEqual(service._normalize_key("Comma"), ",")
        self.assertEqual(service._normalize_key("Period"), ".")
        self.assertEqual(service._normalize_key("Slash"), "/")

    def test_normalize_key_lowercases_unmapped_keys_by_default(self):
        service = self._make_service()

        self.assertEqual(service._normalize_key("Z"), "z")
        self.assertEqual(service._normalize_key("Home"), "home")

    async def test_perform_action_presses_normalized_key_for_resolved_action(self):
        service = self._make_service()
        service.load_keybinds()

        with patch("services.keybinds_service.pydirectinput.press") as mock_press:
            await service.perform_action(EdAction.TOGGLE_FLIGHT_ASSIST)

        mock_press.assert_called_once_with("z")

    async def test_event_bus_publish_of_ed_action_triggers_perform_action(self):
        event_bus = EventBus()
        service = KeybindService(
            keybinds_path=KEYBINDS_PATH,
            event_bus=event_bus,
            settings_handler=self.settings_handler,
        )
        service.load_keybinds()

        with patch("services.keybinds_service.pydirectinput.press") as mock_press:
            await event_bus.publish(EdAction.TOGGLE_FLIGHT_ASSIST)

        mock_press.assert_called_once_with("z")

    def test_validate_settings_returns_issue_when_keybindings_path_empty(self):
        service = self._make_service()
        new_settings = _make_settings(api_key="sk-ant-test")
        new_settings.paths.keybindings_path = ""

        issue = service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "keybindings_path")

    def test_validate_settings_returns_issue_when_no_binds_files_found(self):
        service = self._make_service()
        self.mock_glob.return_value = []
        new_settings = _make_settings(api_key="sk-ant-test")

        issue = service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "keybindings_path")
        self.assertIn("No .binds files found", issue.message)

    def test_validate_settings_returns_no_issues_for_valid_binds_file(self):
        service = self._make_service()
        new_settings = _make_settings(api_key="sk-ant-test")

        issue = service.validate_settings(new_settings)

        self.assertIsNone(issue)

    def test_reload_service_reloads_keybinds_from_settings_handler(self):
        service = self._make_service()
        new_settings = _make_settings(api_key="sk-ant-new")
        self.settings_handler.get_settings.return_value = new_settings

        service.reload_service()

        self.assertEqual(service.keybinds_path, new_settings.paths.keybindings_path)
        self.assertEqual(len(service.get_keybinds()), REQUIRED_KEYBINDS_COUNT)


if __name__ == "__main__":
    unittest.main()
