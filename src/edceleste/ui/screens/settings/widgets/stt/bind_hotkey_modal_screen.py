from __future__ import annotations

from typing import TYPE_CHECKING

from textual import on
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from edceleste.services.models.keybinds_model import (
    Keybind,
    action_in_plain_words,
    find_keybind_using_key,
)
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton

if TYPE_CHECKING:
    from pynput import keyboard, mouse


class BindHotkeyModalScreen(ModalScreen[str | None]):
    caught_key: reactive[str | None] = reactive(None, recompose=True)

    def __init__(self, game_keybinds: list[Keybind], *args, **kwargs) -> None:
        """Dismissed with the caught key as pynput names it ("Key.f9",
        "Button.x1", "'k'") or with None on cancel. Nothing is saved here.
        game_keybinds are the keybinds the game uses now: a caught key that one
        of them uses shows an error and CONFIRM stays disabled."""
        super().__init__(*args, **kwargs)
        self.game_keybinds = game_keybinds
        self._conflict_message: str | None = None
        self._listeners: list[keyboard.Listener | mouse.Listener] = []

    def on_mount(self) -> None:
        self.start_listening()

    def on_unmount(self) -> None:
        for listener in self._listeners:
            listener.stop()

    def compose(self):
        with Vertical(id="bind-hotkey-box") as box:
            box.border_title = "BIND HOTKEY"
            if self.caught_key is None:
                yield Label("Press a key or a mouse button...", id="bind-hotkey-prompt")
            else:
                yield Label(self.caught_key, id="bind-hotkey-key")
                if self._conflict_message is not None:
                    yield Label(self._conflict_message, id="bind-hotkey-error")
                yield WidgetButton("RETRY", id="bind-hotkey-retry-button")
            with Horizontal(id="bind-hotkey-footer"):
                confirm_button = WidgetButton(
                    "CONFIRM", id="bind-hotkey-confirm-button"
                )
                confirm_button.disabled = (
                    self.caught_key is None or self._conflict_message is not None
                )
                yield confirm_button
                yield WidgetButton("CANCEL", id="bind-hotkey-cancel-button")

    def start_listening(self) -> None:
        """Starts a global keyboard listener and a global mouse listener (pynput,
        one thread each), so a key is caught also when the game has focus. They
        run until the modal closes. pynput is imported only here, it does not
        import without a display on Linux."""
        from pynput import keyboard, mouse

        self._listeners = [
            keyboard.Listener(on_press=self.pass_key_to_screen),
            mouse.Listener(on_click=self.pass_click_to_screen),
        ]
        for listener in self._listeners:
            listener.start()

    def pass_key_to_screen(self, key) -> None:
        """Runs on the pynput keyboard thread. Hands the key over to the UI
        thread and waits until it is handled."""
        self.app.call_from_thread(self.catch_key, str(key))

    def pass_click_to_screen(self, x, y, button, is_pressed) -> None:
        """Runs on the pynput mouse thread. Only the press counts, not the
        release. The left, right and middle (wheel) button are skipped, so a
        stray click, e.g. on CANCEL, never becomes the hotkey. Turning the wheel
        is not listened for at all."""
        from pynput import mouse

        if is_pressed and button not in (
            mouse.Button.left,
            mouse.Button.right,
            mouse.Button.middle,
        ):
            self.app.call_from_thread(self.catch_key, str(button))

    def catch_key(self, key_name: str) -> None:
        """Runs on the UI thread. Once a key is caught the next ones are
        ignored, RETRY is the only way to catch another. A key that the game
        already uses is caught too, with an error message, so the pilot sees
        why it cannot be confirmed."""
        if self.caught_key is not None:
            return
        keybind = find_keybind_using_key(key_name, self.game_keybinds)
        if keybind is not None:
            self._conflict_message = (
                f"✗ Already used in the game: {action_in_plain_words(keybind.action)}"
            )
        self.caught_key = key_name

    @on(Button.Pressed, "#bind-hotkey-retry-button")
    def forget_caught_key(self) -> None:
        """Forgets the caught key and its error, so the modal listens again."""
        self._conflict_message = None
        self.caught_key = None

    @on(Button.Pressed, "#bind-hotkey-confirm-button")
    def confirm_caught_key(self) -> None:
        """Closes the modal and hands the caught key to the settings screen."""
        self.dismiss(self.caught_key)

    @on(Button.Pressed, "#bind-hotkey-cancel-button")
    def cancel_binding(self) -> None:
        """Closes the modal without a key."""
        self.dismiss(None)
