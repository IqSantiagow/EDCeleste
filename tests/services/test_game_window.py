import unittest
from ctypes import wintypes
from unittest.mock import AsyncMock, Mock, patch

from edceleste.services.game_window import (
    GAME_WINDOW_TITLE,
    WAIT_AFTER_SWITCH_SECONDS,
    GameWindow,
    load_windows_api,
)

GAME = 42
TERMINAL = 7


class FakeWindowsApi:
    """Pretends to be user32: knows the game window and which window is in front."""

    def __init__(self, game_window, window_in_front, windows_allows_switch=True):
        self.game_window = game_window
        self.window_in_front = window_in_front
        self.windows_allows_switch = windows_allows_switch
        self.searched_titles = []
        self.switched_to = []

    def FindWindowW(self, class_name, window_title):
        self.searched_titles.append(window_title)
        return self.game_window

    def GetForegroundWindow(self):
        return self.window_in_front

    def SetForegroundWindow(self, window):
        self.switched_to.append(window)
        if self.windows_allows_switch:
            self.window_in_front = window
        return self.windows_allows_switch


class GameWindowTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        sleep_patcher = patch(
            "edceleste.services.game_window.asyncio.sleep", new_callable=AsyncMock
        )
        self.mock_sleep = sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    async def test_should_not_switch_or_wait_when_game_is_already_in_front(self):
        windows_api = FakeWindowsApi(game_window=GAME, window_in_front=GAME)

        is_ready = await GameWindow(windows_api).bring_to_front()

        self.assertTrue(is_ready)
        self.assertEqual(windows_api.switched_to, [])
        self.mock_sleep.assert_not_awaited()

    async def test_should_bring_game_to_front_and_wait_when_terminal_is_in_front(self):
        windows_api = FakeWindowsApi(game_window=GAME, window_in_front=TERMINAL)

        is_ready = await GameWindow(windows_api).bring_to_front()

        self.assertTrue(is_ready)
        self.assertEqual(windows_api.switched_to, [GAME])
        self.mock_sleep.assert_awaited_once_with(WAIT_AFTER_SWITCH_SECONDS)

    async def test_should_not_be_ready_when_game_is_not_running(self):
        windows_api = FakeWindowsApi(game_window=None, window_in_front=TERMINAL)

        is_ready = await GameWindow(windows_api).bring_to_front()

        self.assertFalse(is_ready)
        self.assertEqual(windows_api.switched_to, [])

    async def test_should_not_be_ready_when_windows_refuses_the_switch(self):
        windows_api = FakeWindowsApi(
            game_window=GAME, window_in_front=TERMINAL, windows_allows_switch=False
        )

        is_ready = await GameWindow(windows_api).bring_to_front()

        self.assertFalse(is_ready)
        self.assertEqual(windows_api.switched_to, [GAME])

    async def test_should_look_for_the_game_window_by_its_title(self):
        windows_api = FakeWindowsApi(game_window=GAME, window_in_front=GAME)

        await GameWindow(windows_api).bring_to_front()

        self.assertEqual(windows_api.searched_titles, ["Elite - Dangerous (CLIENT)"])
        self.assertEqual(GAME_WINDOW_TITLE, "Elite - Dangerous (CLIENT)")

    async def test_should_never_find_the_game_window_outside_windows(self):
        with patch("edceleste.services.game_window.sys.platform", "linux"):
            game_window = GameWindow(load_windows_api())

        is_ready = await game_window.bring_to_front()

        self.assertFalse(is_ready)

    def test_should_return_window_handles_as_pointers_on_windows(self):
        user32 = Mock()
        with (
            patch("edceleste.services.game_window.sys.platform", "win32"),
            patch(
                "edceleste.services.game_window.ctypes.windll",
                Mock(user32=user32),
                create=True,
            ),
        ):
            windows_api = load_windows_api()

        self.assertIs(windows_api, user32)
        self.assertEqual(user32.FindWindowW.restype, wintypes.HWND)
        self.assertEqual(user32.GetForegroundWindow.restype, wintypes.HWND)
        self.assertEqual(user32.SetForegroundWindow.argtypes, [wintypes.HWND])


if __name__ == "__main__":
    unittest.main()
