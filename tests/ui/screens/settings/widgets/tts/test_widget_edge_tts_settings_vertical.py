import unittest

from textual.app import App, ComposeResult
from textual.widgets import LoadingIndicator, Select

from edceleste.services.models.settings_model import EdgeParamsModel
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_select_row import (
    WidgetLabeledSelectRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_edge_tts_settings_vertical import (  # noqa: E501
    WidgetEdgeTTSSettingsVertical,
)

SAVED_VOICE = "en-US-AriaNeural"
ALL_VOICES = ["en-GB-SoniaNeural", SAVED_VOICE, "pl-PL-ZofiaNeural"]


class FakeSettingsRepository:
    """Gives the voice names, or raises like the network call does when it fails."""

    def __init__(self, voices: list[str] | None) -> None:
        self.voices = voices

    async def fetch_edge_tts_voice_names(self) -> list[str]:
        if self.voices is None:
            raise ConnectionError("no internet")
        return self.voices


class EdgeVoiceApp(App):
    def __init__(self, voices: list[str] | None) -> None:
        super().__init__()
        self.voices = voices

    def compose(self) -> ComposeResult:
        yield WidgetEdgeTTSSettingsVertical(
            EdgeParamsModel(type="edge", voice=SAVED_VOICE),
            settings_repository=FakeSettingsRepository(self.voices),  # type: ignore[arg-type]
        )


class TestWidgetEdgeTTSSettingsVertical(unittest.IsolatedAsyncioTestCase):
    async def test_voice_list_download_fails_shows_saved_voice_without_loading(self):
        app = EdgeVoiceApp(voices=None)
        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertEqual(len(app.query(LoadingIndicator)), 0)
            row = app.query_one(WidgetLabeledSelectRow)
            self.assertEqual(row.options, [SAVED_VOICE])
            self.assertEqual(row.query_one(Select).value, SAVED_VOICE)

    async def test_voice_list_download_works_shows_all_voices_with_saved_one_picked(
        self,
    ):
        app = EdgeVoiceApp(voices=ALL_VOICES)
        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertEqual(len(app.query(LoadingIndicator)), 0)
            row = app.query_one(WidgetLabeledSelectRow)
            self.assertEqual(row.options, ALL_VOICES)
            self.assertEqual(row.query_one(Select).value, SAVED_VOICE)
