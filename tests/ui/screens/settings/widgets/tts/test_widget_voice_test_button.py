import asyncio
import unittest
from unittest.mock import Mock

from textual.app import App, ComposeResult

from edceleste.services.models.settings_model import TTSModel
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.tts.widget_voice_test_button import (
    WidgetVoiceTestButton,
)

TEST_BUTTON = "#voice-test-button"


class FakeSettingsRepository:
    """Waits until the test lets the sound end, so the running state can be
    checked."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.played_settings: list[TTSModel] = []
        self.may_finish = asyncio.Event()

    async def play_voice_test(self, tts_settings: TTSModel) -> None:
        self.played_settings.append(tts_settings)
        await self.may_finish.wait()
        if self.error is not None:
            raise self.error


class VoiceTestApp(App):
    def __init__(self, tts_model: TTSModel, repository: FakeSettingsRepository) -> None:
        super().__init__()
        self.tts_model = tts_model
        self.repository = repository

    def compose(self) -> ComposeResult:
        yield WidgetVoiceTestButton(self.tts_model, self.repository)  # type: ignore[arg-type]


def find_test_button(app: App) -> WidgetButton:
    return app.query_one(TEST_BUTTON, WidgetButton)


class TestWidgetVoiceTestButton(unittest.IsolatedAsyncioTestCase):
    async def test_shows_the_test_voice_button(self):
        app = VoiceTestApp(TTSModel(volume=0.5), FakeSettingsRepository())

        async with app.run_test():
            self.assertEqual(str(find_test_button(app).label), "[▶ Test voice]")
            self.assertFalse(find_test_button(app).disabled)

    async def test_pressing_the_button_plays_the_tts_model_as_it_is_now(self):
        tts_model = TTSModel(volume=0.5, ship_effect=True)
        repository = FakeSettingsRepository()
        app = VoiceTestApp(tts_model, repository)

        async with app.run_test() as pilot:
            tts_model.ship_effect = False
            find_test_button(app).press()
            await pilot.pause()

            self.assertEqual(len(repository.played_settings), 1)
            self.assertIs(repository.played_settings[0], tts_model)
            self.assertFalse(repository.played_settings[0].ship_effect)

            repository.may_finish.set()
            await app.workers.wait_for_complete()

    async def test_a_quick_second_press_does_not_start_a_second_sentence(self):
        repository = FakeSettingsRepository()
        app = VoiceTestApp(TTSModel(volume=0.5), repository)

        async with app.run_test() as pilot:
            find_test_button(app).press()
            find_test_button(app).press()
            await pilot.pause()

            self.assertEqual(len(repository.played_settings), 1)

            repository.may_finish.set()
            await app.workers.wait_for_complete()

    async def test_button_is_disabled_only_while_the_sound_plays(self):
        repository = FakeSettingsRepository()
        app = VoiceTestApp(TTSModel(volume=0.5), repository)

        async with app.run_test() as pilot:
            find_test_button(app).press()
            await pilot.pause()

            self.assertTrue(find_test_button(app).disabled)

            repository.may_finish.set()
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.assertFalse(find_test_button(app).disabled)

    async def test_an_error_of_the_test_shows_a_notification_and_the_button_works_again(
        self,
    ):
        repository = FakeSettingsRepository(error=ValueError("Voice is not set."))
        repository.may_finish.set()
        app = VoiceTestApp(TTSModel(volume=0.5), repository)

        async with app.run_test() as pilot:
            widget = app.query_one(WidgetVoiceTestButton)
            widget.notify = Mock()  # type: ignore[method-assign]

            find_test_button(app).press()
            await app.workers.wait_for_complete()
            await pilot.pause()

            widget.notify.assert_called_once()
            message = widget.notify.call_args.args[0]
            self.assertIn("Voice is not set.", message)
            self.assertEqual(widget.notify.call_args.kwargs["severity"], "error")
            self.assertFalse(find_test_button(app).disabled)


if __name__ == "__main__":
    unittest.main()
