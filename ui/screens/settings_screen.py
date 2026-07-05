from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class SettingsScreen(Screen):
    BINDINGS = [("escape", "pop_screen", "Back")]

    def compose(self):
        yield Header()
        yield Footer()
        yield Static("Settings Screen", id="settings_screen")
