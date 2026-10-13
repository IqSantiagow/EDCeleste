import allure
import pytest
from textual.app import App

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.system_check.system_check_screen import (
    SystemCheckRow,
    SystemCheckScreen,
)
from tests.e2e.test_streaming_voice import chatterbox_settings
from tests.e2e.test_voice_profiles import write_voice_profile_files

pytestmark = [pytest.mark.anyio, allure.feature("Start-up and preflight")]


@allure.title("EDCeleste opens the dashboard after a passing preflight")
async def test_should_open_the_dashboard_after_a_passing_preflight(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("Then the dashboard is open"):
            assert isinstance(pilot.app.screen, DashboardScreen)


@allure.title("EDCeleste stops watching the journal when the Commander quits")
async def test_should_stop_watching_the_journal_when_the_app_closes(edceleste):
    game_watcher_service = edceleste.container.game_watcher_service()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And EDCeleste watches the journal"):
            assert game_watcher_service._game_watcher_tasks != []

        with allure.step("When the Commander quits with Ctrl+C"):
            await pilot.press("ctrl+c")

    with allure.step("Then EDCeleste no longer watches the journal"):
        assert game_watcher_service._game_watcher_tasks == []


def preflight_row(app: App, service_name: str) -> SystemCheckRow:
    return app.screen.query_one(f"#system-check-row-{service_name}", SystemCheckRow)


@allure.title("The preflight stops on an invalid config.yaml")
async def test_should_stop_the_preflight_on_an_invalid_config(edceleste):
    with allure.step("Given config.yaml has no valid settings"):
        edceleste.config_file.write_text("paths: {}")

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks the settings as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "settings").state == "failed",
                    "the settings row marked as failed",
                )
                await pilot.pause()
                assert (
                    preflight_row(pilot.app, "settings").error_message
                    == "Failed to load settings from config.yaml."
                )

            with allure.step("And the preflight stops before the journal check"):
                assert isinstance(pilot.app.screen, SystemCheckScreen)
                assert preflight_row(pilot.app, "game_watcher").state == "pending"


@allure.title("The preflight stops when the journal folder is missing")
async def test_should_stop_the_preflight_when_the_journal_folder_is_missing(
    edceleste, tmp_path
):
    missing_journal_folder = tmp_path / "missing_journal"

    with allure.step("Given the journal path in config.yaml points to no folder"):
        edceleste.settings.paths.journal_path = str(missing_journal_folder)
        edceleste.save_config()

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks the journal check as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "game_watcher").state == "failed",
                    "the game watcher row marked as failed",
                )
                await pilot.pause()
                assert (
                    preflight_row(pilot.app, "game_watcher").error_message
                    == f"No journal files found in '{missing_journal_folder}'."
                )

            with allure.step("And the preflight stops before the keybinds check"):
                assert isinstance(pilot.app.screen, SystemCheckScreen)
                assert preflight_row(pilot.app, "keybinds").state == "pending"


def preflight_progress_texts(app: App, service_name: str) -> list[str]:
    progress_labels = preflight_row(app, service_name).query(".system-check-progress")
    return [str(label.content) for label in progress_labels]


@allure.title("A fast voice engine loads at startup and the preflight says so")
async def test_should_show_loading_the_voice_while_a_fast_voice_engine_loads(
    edceleste,
):
    with allure.step(
        "Given Chatterbox on a GPU is saved with the voice 'narrator' at volume 0.5"
    ):
        write_voice_profile_files(edceleste, "narrator")
        edceleste.save_tts_settings(chatterbox_settings(device="cuda"))
        chatterbox = edceleste.fake_tts_providers["chatterbox"]

    with allure.step("And the voice engine is slow to load the voice"):
        chatterbox.make_the_voice_slow()

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the text-to-speech check says 'Loading the voice'"):
                await edceleste.wait_until(
                    pilot,
                    lambda: (
                        preflight_progress_texts(pilot.app, "tts")
                        == ["Loading the voice"]
                    ),
                    "'Loading the voice' next to the text-to-speech check",
                )
                assert preflight_row(pilot.app, "tts").state == "in_progress"

            with allure.step("And the dashboard is not open yet"):
                assert isinstance(pilot.app.screen, SystemCheckScreen)

            with allure.step("And when the voice engine has loaded the voice"):
                chatterbox.let_the_voice_finish()

            await edceleste.boot_to_dashboard(pilot, step_keyword="Then")

            with allure.step(
                "And the voice engine spoke 'Ready, Commander.' to warm up"
            ):
                assert chatterbox.spoken_texts == ["Ready, Commander."]

            with allure.step("And it used the voice file 'narrator'"):
                assert chatterbox.spoken_profile_paths == [
                    edceleste.voices_folder / "narrator.pt"
                ]

            with allure.step("And no sound came out of the speakers"):
                assert edceleste.fake_speaker.times_opened == 0
                assert edceleste.played_audio == []


@allure.title("A missing voice file shows as a failed text-to-speech check at startup")
async def test_should_mark_text_to_speech_failed_when_the_voice_file_is_missing(
    edceleste, monkeypatch
):
    with allure.step(
        "Given Chatterbox on a GPU is saved with the voice 'narrator' "
        "but the voice file is gone"
    ):
        edceleste.save_tts_settings(chatterbox_settings(device="cuda"))
        assert not (edceleste.voices_folder / "narrator.pt").exists()

    with allure.step("And the preflight stays open 2 s so the results can be read"):
        monkeypatch.setattr(SystemCheckScreen, "SECONDS_BEFORE_DASHBOARD", 2)

    with allure.step("When EDCeleste starts"):
        async with edceleste.run_app() as pilot:
            with allure.step("Then the preflight marks text to speech as failed"):
                await edceleste.wait_until(
                    pilot,
                    lambda: preflight_row(pilot.app, "tts").state == "failed",
                    "the text-to-speech row marked as failed",
                )

            with allure.step("And the message names the missing voice file"):
                assert "narrator.pt" in preflight_row(pilot.app, "tts").error_message

            await edceleste.boot_to_dashboard(pilot, step_keyword="And")
