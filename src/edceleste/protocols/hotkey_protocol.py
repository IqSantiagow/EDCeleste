from typing import Protocol

from edceleste.services.models.hotkey_model import Hotkey


class HotkeyProtocol(Protocol):
    def register_hotkey(self, hotkey: Hotkey) -> None:
        """Starts watching the key everywhere, also when the game has focus.
        hotkey.key_name is spelled as pynput prints a key ("Key.f9", "'k'",
        "Button.x1"). hotkey.on_press runs once when the key goes down
        (holding it does not repeat it), hotkey.on_release when it goes up.
        They run on the listener thread of pynput, the keyboard thread for a
        key and the mouse thread for a mouse button, so not on the UI thread.
        Registering the same key again replaces the old hotkey. Outside Windows
        no listener runs and nothing is ever called."""
        ...

    def unregister_hotkey(self, key_name: str) -> None:
        """Stops watching the key, spelled like in register_hotkey(). Does
        nothing for a key that is not registered. A key held down at that
        moment gets no on_release."""
        ...
