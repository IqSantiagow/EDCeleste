import asyncio
import unittest
from unittest.mock import Mock

from textual.app import App, ComposeResult

from edceleste.services.models.settings_model import TTSModel, VoiceLabModel
from edceleste.ui.screens.settings.widgets.inputs.widget_button import WidgetButton
from edceleste.ui.screens.settings.widgets.inputs.widget_labeled_slider_row import (
    WidgetLabeledSliderRow,
)
from edceleste.ui.screens.settings.widgets.tts.widget_voice_lab_settings_vertical import (  # noqa: E501
    VoiceLabInputWidgetIds,
    WidgetVoiceLabSettingsVertical,
)

TEST_BUTTON = "#voice-lab-test-button"


class FakeSettingsRepository:
    """Waits until the test lets the sound end, so the running state can be
    checked."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.played_settings: list[TTSModel] = []
        self.may_finish = asyncio.Event()

    async def play_voice_lab_test(self, tts_settings: TTSModel) -> None:
        self.played_settings.append(tts_settings)
        await self.may_finish.wait()
        if self.error is not None:
            raise self.error


class VoiceLabTestApp(App):
    def __init__(self, tts_model: TTSModel, repository: FakeSettingsRepository) -> None:
        super().__init__()
        self.tts_model = tts_model
        self.repository = repository

    def compose(self) -> ComposeResult:
        yield WidgetVoiceLabSettingsVertical(self.tts_model, self.repository)  # type: ignore[arg-type]


def make_tts_model(voice_lab: VoiceLabModel | None = None) -> TTSModel:
    return TTSModel(volume=0.5, voice_lab=voice_lab or VoiceLabModel())


def find_test_button(app: App) -> WidgetButton:
    return app.query_one(TEST_BUTTON, WidgetButton)


class TestWidgetVoiceLabSettingsVertical(unittest.IsolatedAsyncioTestCase):
    async def test_shows_the_test_button_below_the_sliders(self):
        app = VoiceLabTestApp(make_tts_model(), FakeSettingsRepository())

        async with app.run_test():
            widget = app.query_one(WidgetVoiceLabSettingsVertical)

            self.assertEqual(str(find_test_button(app).label), "[▶ Test voice]")
            self.assertIs(widget.children[-1], find_test_button(app))

    async def test_hides_the_sliders_but_not_the_test_button_when_effects_are_off(
        self,
    ):
        app = VoiceLabTestApp(
            make_tts_model(VoiceLabModel(enabled=False)), FakeSettingsRepository()
        )

        async with app.run_test():
            slider_rows = app.query(WidgetLabeledSliderRow)

            self.assertEqual(len(slider_rows), 3)
            self.assertTrue(all(not row.display for row in slider_rows))
            self.assertTrue(find_test_button(app).display)

    async def test_sliders_show_the_values_of_the_tts_model(self):
        voice_lab = VoiceLabModel(clarity=0.25, reverb=0.75, stereo_width=0.1)
        app = VoiceLabTestApp(make_tts_model(voice_lab), FakeSettingsRepository())

        async with app.run_test():
            values = {
                widget_id: app.query_one(f"#{widget_id}", WidgetLabeledSliderRow).value
                for widget_id in (
                    VoiceLabInputWidgetIds.VOICE_LAB_CLARITY_INPUT,
                    VoiceLabInputWidgetIds.VOICE_LAB_REVERB_INPUT,
                    VoiceLabInputWidgetIds.VOICE_LAB_STEREO_WIDTH_INPUT,
                )
            }

            self.assertEqual(
                values,
                {
                    VoiceLabInputWidgetIds.VOICE_LAB_CLARITY_INPUT: 0.25,
                    VoiceLabInputWidgetIds.VOICE_LAB_REVERB_INPUT: 0.75,
                    VoiceLabInputWidgetIds.VOICE_LAB_STEREO_WIDTH_INPUT: 0.1,
                },
            )

    async def test_pressing_the_test_button_plays_the_tts_model_as_it_is_now(self):
        tts_model = make_tts_model()
        repository = FakeSettingsRepository()
        app = VoiceLabTestApp(tts_model, repository)

        async with app.run_test() as pilot:
            tts_model.voice_lab.clarity = 0.9
            find_test_button(app).press()
            await pilot.pause()

            self.assertEqual(len(repository.played_settings), 1)
            self.assertIs(repository.played_settings[0], tts_model)
            self.assertEqual(repository.played_settings[0].voice_lab.clarity, 0.9)

            repository.may_finish.set()
            await app.workers.wait_for_complete()

    async def test_test_button_is_disabled_only_while_the_sound_plays(
        self,
    ):
        repository = FakeSettingsRepository()
        app = VoiceLabTestApp(make_tts_model(), repository)

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
        app = VoiceLabTestApp(make_tts_model(), repository)

        async with app.run_test() as pilot:
            widget = app.query_one(WidgetVoiceLabSettingsVertical)
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
