import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

from edceleste.services.hotkey_service import HotkeyService
from edceleste.services.models.hotkey_model import Hotkey

HOTKEY_LOGGER = "edceleste.services.hotkey_service"


def _make_service_without_listeners() -> HotkeyService:
    """Built as on Linux, so no real keyboard or mouse listener starts."""
    with patch.object(sys, "platform", "linux"):
        return HotkeyService()


def _make_hotkey(key_name: str = "Key.f9", **callbacks) -> Hotkey:
    return Hotkey(
        key_name=key_name,
        on_press=callbacks.get("on_press", Mock()),
        on_release=callbacks.get("on_release", Mock()),
    )


class TestHotkeyServiceKeys(unittest.TestCase):
    def setUp(self):
        self.service = _make_service_without_listeners()

    def test_pressing_registered_key_calls_on_press(self):
        hotkey = _make_hotkey()
        self.service.register_hotkey(hotkey)

        self.service._on_key_down("Key.f9")

        hotkey.on_press.assert_called_once_with()
        hotkey.on_release.assert_not_called()

    def test_holding_key_calls_on_press_only_once(self):
        hotkey = _make_hotkey()
        self.service.register_hotkey(hotkey)

        for _ in range(3):
            self.service._on_key_down("Key.f9")

        hotkey.on_press.assert_called_once_with()

    def test_releasing_key_calls_on_release(self):
        hotkey = _make_hotkey()
        self.service.register_hotkey(hotkey)
        self.service._on_key_down("Key.f9")

        self.service._on_key_up("Key.f9")

        hotkey.on_release.assert_called_once_with()

    def test_release_without_press_does_not_call_on_release(self):
        hotkey = _make_hotkey()
        self.service.register_hotkey(hotkey)

        self.service._on_key_up("Key.f9")

        hotkey.on_release.assert_not_called()

    def test_key_can_be_pressed_again_after_release(self):
        hotkey = _make_hotkey()
        self.service.register_hotkey(hotkey)
        self.service._on_key_down("Key.f9")
        self.service._on_key_up("Key.f9")

        self.service._on_key_down("Key.f9")

        self.assertEqual(hotkey.on_press.call_count, 2)

    def test_unregistered_key_is_ignored(self):
        hotkey = _make_hotkey("Key.f9")
        self.service.register_hotkey(hotkey)

        self.service._on_key_down("Key.f10")
        self.service._on_key_up("Key.f10")

        hotkey.on_press.assert_not_called()
        hotkey.on_release.assert_not_called()

    def test_unregister_hotkey_stops_calling_callbacks(self):
        hotkey = _make_hotkey()
        self.service.register_hotkey(hotkey)

        self.service.unregister_hotkey("Key.f9")
        self.service._on_key_down("Key.f9")
        self.service._on_key_up("Key.f9")

        hotkey.on_press.assert_not_called()
        hotkey.on_release.assert_not_called()

    def test_unregister_unknown_key_does_nothing(self):
        self.service.unregister_hotkey("Key.never_registered")

    def test_registering_same_key_again_replaces_callbacks(self):
        old_hotkey = _make_hotkey()
        new_hotkey = _make_hotkey()
        self.service.register_hotkey(old_hotkey)
        self.service.register_hotkey(new_hotkey)

        self.service._on_key_down("Key.f9")

        new_hotkey.on_press.assert_called_once_with()
        old_hotkey.on_press.assert_not_called()

    def test_error_in_on_press_is_logged_not_raised(self):
        hotkey = _make_hotkey(on_press=Mock(side_effect=RuntimeError("boom")))
        self.service.register_hotkey(hotkey)

        with self.assertLogs(HOTKEY_LOGGER, level="ERROR"):
            self.service._on_key_down("Key.f9")

    def test_error_in_on_release_is_logged_not_raised(self):
        hotkey = _make_hotkey(on_release=Mock(side_effect=RuntimeError("boom")))
        self.service.register_hotkey(hotkey)
        self.service._on_key_down("Key.f9")

        with self.assertLogs(HOTKEY_LOGGER, level="ERROR"):
            self.service._on_key_up("Key.f9")

    def test_mouse_button_press_and_release_work_like_a_key(self):
        hotkey = _make_hotkey("Button.x1")
        self.service.register_hotkey(hotkey)

        self.service._on_mouse_click(0, 0, "Button.x1", True)
        hotkey.on_press.assert_called_once_with()
        hotkey.on_release.assert_not_called()

        self.service._on_mouse_click(0, 0, "Button.x1", False)
        hotkey.on_release.assert_called_once_with()


class TestHotkeyServiceListeners(unittest.TestCase):
    def test_listeners_start_on_windows(self):
        fake_pynput = MagicMock()

        with (
            patch.dict(sys.modules, {"pynput": fake_pynput}),
            patch.object(sys, "platform", "win32"),
        ):
            service = HotkeyService()

        fake_pynput.keyboard.Listener.assert_called_once_with(
            on_press=service._on_key_down, on_release=service._on_key_up
        )
        fake_pynput.keyboard.Listener.return_value.start.assert_called_once_with()
        fake_pynput.mouse.Listener.assert_called_once_with(
            on_click=service._on_mouse_click
        )
        fake_pynput.mouse.Listener.return_value.start.assert_called_once_with()

    def test_no_listener_starts_outside_windows(self):
        fake_pynput = MagicMock()

        with (
            patch.dict(sys.modules, {"pynput": fake_pynput}),
            patch.object(sys, "platform", "linux"),
        ):
            HotkeyService()

        fake_pynput.keyboard.Listener.assert_not_called()
        fake_pynput.mouse.Listener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
