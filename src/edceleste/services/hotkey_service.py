import logging
import sys

from edceleste.services.models.hotkey_model import Hotkey

logger = logging.getLogger(__name__)


class HotkeyService:
    def __init__(self) -> None:
        """Starts the global keyboard listener and the global mouse listener
        (pynput, each on its own daemon thread), which run until the app ends
        and cannot be stopped. Outside Windows no listener starts, so the
        service can be built in tests and CI. pynput is imported only here, it
        does not import without a display on Linux. An error of the import or
        of the start is not caught.

        The registry of hotkeys is empty. The service knows no settings,
        whoever owns a key registers it with register_hotkey() and removes it
        with unregister_hotkey().
        """
        self._hotkeys_by_key_name: dict[str, Hotkey] = {}
        if sys.platform == "win32":
            from pynput import keyboard, mouse

            keyboard.Listener(
                on_press=self._on_key_down, on_release=self._on_key_up
            ).start()
            mouse.Listener(on_click=self._on_mouse_click).start()

    def register_hotkey(self, hotkey: Hotkey) -> None:
        """Stores the hotkey under hotkey.key_name, which is spelled as pynput
        prints a key: "Key.f9", "'k'" or "Button.x1". A key registered again
        replaces the old hotkey, a key held down at that moment gets no
        on_release from the old one. Nothing is checked, a name that pynput
        never prints is simply never called."""
        self._hotkeys_by_key_name[hotkey.key_name] = hotkey
        logger.info("Hotkey '%s' registered.", hotkey.key_name)

    def unregister_hotkey(self, key_name: str) -> None:
        """Stops watching the key, e.g. after the pilot chose another one in
        the settings. key_name is spelled like in register_hotkey(). Does
        nothing for a key that is not registered. A key held down at that
        moment gets no on_release."""
        self._hotkeys_by_key_name.pop(key_name, None)
        logger.info("Hotkey '%s' unregistered.", key_name)

    def _on_mouse_click(self, x, y, button, is_pressed) -> None:
        """Called by pynput on the mouse thread for every mouse button going
        down or up. A button is handled like a key, its name is e.g.
        "Button.x1": pressed goes to _on_key_down(), released to _on_key_up().
        x and y are ignored. The hotkey callbacks of a mouse button therefore
        run on the mouse thread, not on the keyboard thread."""
        if is_pressed:
            self._on_key_down(button)
        else:
            self._on_key_up(button)

    def _on_key_down(self, key) -> None:
        """Called by pynput on its thread for every key going down. Windows
        repeats it while the key is held, so only the first one calls
        on_press. A key that is not registered is ignored. An error in the
        callback is only logged, an error raised here would stop the pynput
        listener for good."""
        hotkey = self._hotkeys_by_key_name.get(str(key))
        if hotkey is None or hotkey.is_held_down:
            return
        hotkey.is_held_down = True
        try:
            hotkey.on_press()
        except Exception:
            logger.exception("The press of hotkey '%s' failed.", hotkey.key_name)

    def _on_key_up(self, key) -> None:
        """Called by pynput on its thread for every key going up. Calls
        on_release only for a registered key that was seen going down. An
        error in the callback is only logged, like in _on_key_down()."""
        hotkey = self._hotkeys_by_key_name.get(str(key))
        if hotkey is None or not hotkey.is_held_down:
            return
        hotkey.is_held_down = False
        try:
            hotkey.on_release()
        except Exception:
            logger.exception("The release of hotkey '%s' failed.", hotkey.key_name)
