from collections.abc import Callable

from pydantic import BaseModel


class Hotkey(BaseModel):
    """
    One key that HotkeyService watches everywhere, also when the game has
    focus. The same object is kept by the service as the state of that key.

    key_name is the text pynput gives for the key: "Key.f9", "Key.ctrl_l",
    "'k'" for a normal key or "Button.x1" for a mouse button. on_press runs
    once when the key goes down, on_release when it goes up. Both run on the
    listener thread of pynput.
    """

    key_name: str
    on_press: Callable[[], None]
    on_release: Callable[[], None]
    is_held_down: bool = False
