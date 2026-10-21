Agent had a task to implement simple hotkey service that could register and unregister hotkeys, and handle key press and release events.

First version he did:
```python
class HotkeyService:
    def __init__(self) -> None:
        """Only prepares empty state. No keyboard listener runs until the first
        register_hotkey()."""
        self._callbacks_by_key: dict[
            str, tuple[Callable[[], None], Callable[[], None]]
        ] = {}
        self._keys_held_down: set[str] = set()
        self._app_loop: asyncio.AbstractEventLoop | None = None
        self._listener: keyboard.Listener | None = None

    def register_hotkey(
        self,
        key_name: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        """Starts watching one key everywhere, also when the game has focus.

        1. Remembers the running event loop, the callbacks must run on it.
           Raises RuntimeError when called outside the event loop.
        2. Stores the callbacks under the key name. The same key registered
           again replaces the old callbacks.
        3. Starts the global keyboard listener (its own thread) when it does
           not run yet.

        key_name is the pynput name in lowercase: "f9", "ctrl_l", "caps_lock"
        or a single character such as "k".
        """
        self._app_loop = asyncio.get_running_loop()
        self._callbacks_by_key[key_name] = (on_press, on_release)
        if self._listener is None:
            self._listener = keyboard.Listener(
                on_press=self._on_key_down, on_release=self._on_key_up
            )
            self._listener.start()
            logger.info("Global keyboard listener started.")
        logger.info("Hotkey '%s' registered.", key_name)

    def unregister_hotkey(self, key_name: str) -> None:
        """Forgets the key. Does nothing for a key that is not registered.
        Stops the keyboard listener when it was the last registered key. A key
        held down at that moment gets no on_release."""
        self._callbacks_by_key.pop(key_name, None)
        self._keys_held_down.discard(key_name)
        if not self._callbacks_by_key and self._listener is not None:
            self._listener.stop()
            self._listener = None
            logger.info("Global keyboard listener stopped.")
        logger.info("Hotkey '%s' unregistered.", key_name)

    def _on_key_down(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """Called by pynput on the listener thread for every key going down.
        Windows repeats this event all the time a key is held, so only the
        first one of a hold is passed on, the rest is dropped until the key
        goes up. A key that is not registered is ignored."""
        key_name = self._read_key_name(key)
        if key_name not in self._callbacks_by_key or key_name in self._keys_held_down:
            return
        self._keys_held_down.add(key_name)
        on_press, _ = self._callbacks_by_key[key_name]
        self._run_on_app_loop(on_press)

    def _on_key_up(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        """Called by pynput on the listener thread for every key going up.
        Passes on_release on only for a registered key that was seen going down
        before, so a key already held when it was registered gives no
        release."""
        key_name = self._read_key_name(key)
        if key_name not in self._keys_held_down:
            return
        self._keys_held_down.discard(key_name)
        _, on_release = self._callbacks_by_key[key_name]
        self._run_on_app_loop(on_release)

    def _run_on_app_loop(self, callback: Callable[[], None]) -> None:
        """Hands the callback from the listener thread to the event loop, which
        runs it soon after. Never runs it on the listener thread. An error in
        the callback is logged by the event loop."""
        assert self._app_loop is not None
        self._app_loop.call_soon_threadsafe(callback)

    def _read_key_name(self, key: keyboard.Key | keyboard.KeyCode | None) -> str | None:
        """The name used in register_hotkey(): the pynput name for a special
        key ("f9", "ctrl_l"), the lowercase character for a normal key ("k").
        None for a key that has neither, e.g. a numpad key, so it can never be
        registered."""
        if isinstance(key, keyboard.Key):
            return key.name
        if isinstance(key, keyboard.KeyCode) and key.char:
            return key.char.lower()
        return None
```


My version coded manually:

```python
class HotkeyService:
    def __init__(
        self,
        event_bus: EventBus,
    ):
        self.event_bus = event_bus
        self.registered_hotkeys: dict[str, Hotkey] = {}
        self.event_bus.subscribe(Hotkey, self.register_hotkey)

        self.keyboard_listener = KeyboardListener(
            on_press=self.on_key_down, on_release=self.on_key_up
        )
        self.keyboard_listener.start()

        self.mouse_listener = MouseListener(on_click=self.on_mouse_click)
        self.mouse_listener.start()

    async def register_hotkey(self, hotkey: Hotkey):
        self.registered_hotkeys[hotkey.key] = Hotkey(
            key=hotkey.key,
            on_press=hotkey.on_press,
            on_release=hotkey.on_release,
        )

    def unregister_hotkey(self, key):
        if key in self.registered_hotkeys:
            del self.registered_hotkeys[key]

    def on_key_down(self, key):
        key = str(key)
        if key in self.registered_hotkeys:
            hotkey = self.registered_hotkeys[key]
            if not hotkey.is_down:
                hotkey.is_down = True
                hotkey.on_press()

    def on_key_up(self, key):
        key = str(key)
        if key in self.registered_hotkeys:
            hotkey = self.registered_hotkeys[key]
            if hotkey.is_down:
                hotkey.is_down = False
                hotkey.on_release()

    def on_mouse_click(self, x, y, button, pressed):
        key = str(button)
        if key in self.registered_hotkeys:
            hotkey = self.registered_hotkeys[key]
            if pressed and not hotkey.is_down:
                hotkey.is_down = True
                hotkey.on_press()
            elif not pressed and hotkey.is_down:
                hotkey.is_down = False
                hotkey.on_release()
```


Final result after refining an agent:

```python
class HotkeyService:
    def __init__(self, event_bus: EventBus) -> None:
        """Subscribes to the event bus and starts the global keyboard listener
        and the global mouse listener (each on its own thread), which run until
        the app ends.

        Subscriptions:
        - RegisterHotkeyEvent -> register_hotkey
        """
        self._hotkeys_by_key_name: dict[str, RegisterHotkeyEvent] = {}
        event_bus.subscribe(RegisterHotkeyEvent, self.register_hotkey)
        keyboard.Listener(
            on_press=self._on_key_down, on_release=self._on_key_up
        ).start()
        mouse.Listener(on_click=self._on_mouse_click).start()

    async def register_hotkey(self, event: RegisterHotkeyEvent) -> None:
        """Runs when a RegisterHotkeyEvent is published. Stores the event under
        its key name, a key registered again replaces the old one."""
        self._hotkeys_by_key_name[event.key_name] = event
        logger.info("Hotkey '%s' registered.", event.key_name)

    def unregister_hotkey(self, key_name: str) -> None:
        """Stops watching the key, e.g. after the pilot chose another one in
        the settings. Does nothing for a key that is not registered."""
        self._hotkeys_by_key_name.pop(key_name, None)
        logger.info("Hotkey '%s' unregistered.", key_name)

    def _on_mouse_click(self, x, y, button, is_pressed) -> None:
        """Called by pynput on the mouse thread for every mouse button going
        down or up. A button is handled like a key, its name is e.g.
        "Button.x1"."""
        if is_pressed:
            self._on_key_down(button)
        else:
            self._on_key_up(button)

    def _on_key_down(self, key) -> None:
        """Called by pynput on its thread for every key going down. Windows
        repeats it while the key is held, so only the first one calls
        on_press. A key that is not registered is ignored. An error in the
        callback stops the pynput listener."""
        hotkey = self._hotkeys_by_key_name.get(str(key))
        if hotkey is None or hotkey.is_held_down:
            return
        hotkey.is_held_down = True
        hotkey.on_press()

    def _on_key_up(self, key) -> None:
        """Called by pynput on its thread for every key going up. Calls
        on_release only for a registered key that was seen going down."""
        hotkey = self._hotkeys_by_key_name.get(str(key))
        if hotkey is None or not hotkey.is_held_down:
            return
        hotkey.is_held_down = False
        hotkey.on_release()
```


So it is POSSIBLE TO CODE LIKE A NORMAL PERSON NOT A ZUCKERBERG ON DRUGS