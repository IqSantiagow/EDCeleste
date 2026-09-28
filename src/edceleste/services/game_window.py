import asyncio
import ctypes
import logging
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)

GAME_WINDOW_TITLE = "Elite - Dangerous (CLIENT)"
# Windows needs a moment to finish the switch before the game takes key presses
WAIT_AFTER_SWITCH_SECONDS = 0.15


class _WindowsApiStub:
    """Used outside Windows: the game can't run there, so its window is never found."""

    def FindWindowW(self, class_name: str | None, window_title: str) -> int | None:
        return None

    def GetForegroundWindow(self) -> int | None:
        return None

    def SetForegroundWindow(self, window: int) -> bool:
        return False


def load_windows_api():
    """The user32 window calls on Windows, the stub everywhere else."""
    if sys.platform != "win32":
        return _WindowsApiStub()

    user32 = ctypes.windll.user32
    # A window handle is a pointer, the default int return type would cut it in half
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    return user32


class GameWindow:
    """Brings the game window to the front, so a key press lands in the game."""

    def __init__(self, windows_api=None) -> None:
        # Tests pass a fake here instead of the real user32
        self.windows_api = windows_api or load_windows_api()

    async def bring_to_front(self) -> bool:
        """True when the game window has focus and a key press will land in it."""
        game_window = self.windows_api.FindWindowW(None, GAME_WINDOW_TITLE)
        if not game_window:
            logger.warning("Game window not found, is the game running?")
            return False

        # Already in front: no switch, so voice commands don't pay for the wait
        if self.windows_api.GetForegroundWindow() == game_window:
            return True

        self.windows_api.SetForegroundWindow(game_window)
        await asyncio.sleep(WAIT_AFTER_SWITCH_SECONDS)

        # Windows can refuse the switch for an app in the background, so check it
        if self.windows_api.GetForegroundWindow() != game_window:
            logger.warning("Windows did not bring the game window to the front")
            return False

        logger.info("Brought the game window to the front")
        return True
