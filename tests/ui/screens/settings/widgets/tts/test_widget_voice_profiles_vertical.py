import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Button, Label, Select, Static

from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.models.settings_model import PocketParamsModel
from edceleste.ui.screens.settings.widgets.inputs.input_value_changed_event import (
    ValueChanged,
)
from edceleste.ui.screens.settings.widgets.tts.voice_clone_modal_screen import (
    VoiceCloneSaveResult,
)
from edceleste.ui.screens.settings.widgets.tts.widget_voice_profiles_vertical import (
    ProfileRow,
    WidgetVoiceProfilesVertical,
)

MODULE = "edceleste.ui.screens.settings.widgets.tts.widget_voice_profiles_vertical"


class FakeSettingsRepository:
    """Keeps the voice profiles in a list and notes what the widget asked."""

    def __init__(self, profiles: list[str]) -> None:
        self.profiles = profiles
        self.listed_params: list = []
        self.removed: list[tuple] = []
        self.played: list[tuple] = []
        self.remove_error: Exception | None = None
        self.play_error: Exception | None = None

    def get_available_voice_profiles(self, params) -> list[str]:
        self.listed_params.append(params)
        return list(self.profiles)

    def remove_voice_profile(self, profile_name, params) -> None:
        if self.remove_error is not None:
            raise self.remove_error
        self.removed.append((profile_name, params))
        self.profiles.remove(profile_name)

    async def play_sample_voice(self, profile_name, params) -> None:
        if self.play_error is not None:
            raise self.play_error
        self.played.append((profile_name, params))


class ProfilesApp(App):
    def __init__(self, params, repository: FakeSettingsRepository) -> None:
        super().__init__()
        self.params = params
        self.repository = repository

    def compose(self) -> ComposeResult:
        yield WidgetVoiceProfilesVertical(
            self.params,
            settings_repository=self.repository,  # type: ignore[arg-type]
        )

    def on_value_changed(self, message: ValueChanged) -> None:
        """Does what the TTS section does: writes the picked profile into the
        params of the screen."""
        if message.sender_id == "tts-profile-input":
            self.params.profile = message.new_value


def make_params(profile: str = "nova") -> PocketParamsModel:
    return PocketParamsModel(type="pocket", profile=profile)


def profile_names_shown(app: App) -> list[str]:
    return [str(label.content) for label in app.query(".profile-name").results(Label)]


def press(app: App, selector: str, row_number: int = 0) -> None:
    app.query(ProfileRow)[row_number].query_one(selector, Button).press()


class TestWidgetVoiceProfilesVertical(unittest.IsolatedAsyncioTestCase):
    async def test_shows_the_profiles_of_the_engine_on_the_screen(self):
        params = make_params("nova")
        repository = FakeSettingsRepository(["celeste", "nova"])
        app = ProfilesApp(params, repository)

        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertEqual(profile_names_shown(app), ["⧉ celeste", "⧉ nova"])
            self.assertEqual(
                app.query_one("#tts-profile-input Select", Select).value, "nova"
            )
        self.assertIs(repository.listed_params[0], params)

    async def test_shows_a_hint_when_the_engine_has_no_profiles(self):
        app = ProfilesApp(make_params(""), FakeSettingsRepository([]))

        async with app.run_test() as pilot:
            await pilot.pause()

            self.assertEqual(len(app.query(ProfileRow)), 0)
            self.assertEqual(
                len(list(app.query(".no-profiles-message").results(Static))), 1
            )

    async def test_deleting_a_profile_reloads_the_list(self):
        params = make_params("nova")
        repository = FakeSettingsRepository(["celeste", "nova"])
        app = ProfilesApp(params, repository)

        async with app.run_test() as pilot:
            await pilot.pause()
            press(app, ".profile-delete-button", row_number=0)
            await pilot.pause()
            await pilot.pause()

            self.assertEqual(repository.removed, [("celeste", params)])
            self.assertEqual(profile_names_shown(app), ["⧉ nova"])
            self.assertEqual(len(repository.listed_params), 2)

    async def test_a_failed_delete_keeps_the_row_and_shows_the_error(self):
        repository = FakeSettingsRepository(["celeste"])
        repository.remove_error = VoiceCloningException("This engine cannot clone.")
        app = ProfilesApp(make_params(), repository)

        async with app.run_test() as pilot:
            await pilot.pause()
            with patch.object(ProfileRow, "notify") as notify:
                press(app, ".profile-delete-button")
                await pilot.pause()

            notify.assert_called_once_with(
                "This engine cannot clone.", severity="error"
            )
            self.assertEqual(profile_names_shown(app), ["⧉ celeste"])
            self.assertEqual(len(repository.listed_params), 1)

    async def test_play_gives_the_profile_and_the_params_of_the_screen(self):
        params = make_params()
        repository = FakeSettingsRepository(["celeste"])
        app = ProfilesApp(params, repository)

        async with app.run_test() as pilot:
            await pilot.pause()
            press(app, ".profile-play-button")
            await pilot.pause()
            await app.workers.wait_for_complete()

        self.assertEqual(repository.played, [("celeste", params)])

    async def test_play_without_a_sample_shows_a_notification(self):
        repository = FakeSettingsRepository(["celeste"])
        repository.play_error = FileNotFoundError("no sample")
        app = ProfilesApp(make_params(), repository)

        async with app.run_test() as pilot:
            await pilot.pause()
            with patch.object(ProfileRow, "notify") as notify:
                press(app, ".profile-play-button")
                await pilot.pause()
                await app.workers.wait_for_complete()

            notify.assert_called_once_with("No sample audio found for 'celeste'.")

    async def test_play_of_an_engine_that_cannot_clone_shows_a_notification(self):
        repository = FakeSettingsRepository(["celeste"])
        repository.play_error = VoiceCloningException("This engine cannot clone.")
        app = ProfilesApp(make_params(), repository)

        async with app.run_test() as pilot:
            await pilot.pause()
            with patch.object(ProfileRow, "notify") as notify:
                press(app, ".profile-play-button")
                await pilot.pause()
                await app.workers.wait_for_complete()

            notify.assert_called_once_with(
                "This engine cannot clone.", severity="error"
            )

    async def test_the_clone_button_opens_the_clone_window_for_the_engine_on_the_screen(
        self,
    ):
        params = make_params()
        app = ProfilesApp(params, FakeSettingsRepository([]))

        async with app.run_test() as pilot:
            await pilot.pause()
            with patch(f"{MODULE}.VoiceCloneModalScreen") as clone_window:
                with patch.object(app, "push_screen") as push_screen:
                    app.query_one("#clone-voice-button", Button).press()
                    await pilot.pause()

            clone_window.assert_called_once_with(params)
            push_screen.assert_called_once()
            self.assertIs(push_screen.call_args.args[0], clone_window.return_value)

    async def test_a_cloned_profile_is_listed_but_not_picked_when_not_set_active(self):
        repository = FakeSettingsRepository(["celeste"])
        app = ProfilesApp(make_params("celeste"), repository)

        async with app.run_test() as pilot:
            await pilot.pause()
            repository.profiles.append("fresh")
            app.query_one(
                WidgetVoiceProfilesVertical
            ).show_cloned_profile_unless_clone_window_was_cancelled(
                VoiceCloneSaveResult(profile_name="fresh", set_as_active=False)
            )
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.assertEqual(profile_names_shown(app), ["⧉ celeste", "⧉ fresh"])
            self.assertEqual(
                app.query_one("#tts-profile-input Select", Select).value, "celeste"
            )

    async def test_a_cancelled_clone_window_changes_nothing(self):
        repository = FakeSettingsRepository(["celeste"])
        app = ProfilesApp(make_params("celeste"), repository)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one(
                WidgetVoiceProfilesVertical
            ).show_cloned_profile_unless_clone_window_was_cancelled(None)
            await pilot.pause()

            self.assertEqual(len(repository.listed_params), 1)


if __name__ == "__main__":
    unittest.main()
