import unittest
from unittest.mock import patch

from services.keybinds_service import KeybindService
from tests import TEST_BINDS_FILE_LOCATION

KEYBINDS_PATH = "C:/keybinds"
REQUIRED_KEYBINDS_COUNT = 41


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

    def _make_service(self):
        return KeybindService(keybinds_path=KEYBINDS_PATH)

    async def test_should_raise_file_not_found_error_when_no_binds_files_found(self):
        self.mock_glob.return_value = []

        service = self._make_service()

        with self.assertRaises(FileNotFoundError):
            await service.load_keybinds()

        self.assertEqual(service.get_keybinds(), [])

    async def test_should_select_latest_binds_file_by_modification_time(self):
        self.mock_glob.return_value = [
            f"{KEYBINDS_PATH}/older.binds",
            f"{KEYBINDS_PATH}/newer.binds",
        ]
        self.mock_getmtime.side_effect = [100, 200]

        with patch("services.keybinds_service.etree.parse") as mock_parse:
            mock_parse.return_value.getroot.return_value = []

            service = self._make_service()
            await service.load_keybinds()

            mock_parse.assert_called_once_with(f"{KEYBINDS_PATH}/newer.binds")

    async def test_should_load_only_required_keybinds_from_binds_file(self):
        service = self._make_service()

        await service.load_keybinds()

        keybinds = service.get_keybinds()
        self.assertEqual(len(keybinds), REQUIRED_KEYBINDS_COUNT)

        keybinds_by_action = {kb.action: kb.key for kb in keybinds}
        self.assertEqual(keybinds_by_action["ToggleFlightAssist"], "Z")
        self.assertEqual(keybinds_by_action["UIFocus"], "LeftShift")
        self.assertEqual(keybinds_by_action["QuickCommsPanel"], "Enter")
        # Regression check: these keys end in characters ('e', 'y') that also
        # appear in the "Key_" prefix, so a naive str.strip("Key_") call would
        # incorrectly eat into the key name itself (e.g. "Home" -> "Hom").
        self.assertEqual(keybinds_by_action["ToggleCargoScoop"], "Home")
        self.assertEqual(keybinds_by_action["ExplorationFSSEnter"], "Apostrophe")
        self.assertNotIn("YawLeftButton", keybinds_by_action)

    async def test_should_strip_key_prefix_from_all_loaded_keys(self):
        service = self._make_service()

        await service.load_keybinds()

        for keybind in service.get_keybinds():
            self.assertFalse(keybind.key.startswith("Key_"))

    async def test_should_replace_keybinds_when_load_keybinds_called_twice(self):
        service = self._make_service()

        await service.load_keybinds()
        await service.load_keybinds()

        self.assertEqual(len(service.get_keybinds()), REQUIRED_KEYBINDS_COUNT)

    async def test_get_keybinds_returns_copy_not_internal_list(self):
        service = self._make_service()
        await service.load_keybinds()

        returned = service.get_keybinds()
        returned.clear()

        self.assertEqual(len(service.get_keybinds()), REQUIRED_KEYBINDS_COUNT)

    def test_get_keybinds_returns_empty_list_before_load(self):
        service = self._make_service()

        self.assertEqual(service.get_keybinds(), [])


if __name__ == "__main__":
    unittest.main()
