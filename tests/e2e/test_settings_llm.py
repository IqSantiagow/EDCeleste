import allure
import pytest
from textual.app import App
from textual.pilot import Pilot
from textual.widgets import Input, Label

from tests.e2e.conftest import open_settings_section
from tests.e2e.test_settings import (
    JOURNAL_PATH_ROW,
    path_is_shown_without_yellow,
    save_state_text,
    section_shows_modified_indicator,
)

pytestmark = [pytest.mark.anyio, allure.feature("Settings")]

API_KEY_ROW = "llm-api-key-input"
BASE_URL_ROW = "llm-base-url-input"
MODEL_ROW = "llm-model-input"
CONNECTED = "✓ Connected"


def model_list_is_loading(app: App) -> bool:
    return len(app.screen.query("#loading-llm-models-indicator")) == 1


def model_list_is_shown(app: App) -> bool:
    return len(app.screen.query(f"#{MODEL_ROW}")) == 1 and not model_list_is_loading(
        app
    )


def connection_result(app: App) -> str:
    return str(app.screen.query_one("#test-connection-result", Label).content)


def row_is_a_text_again(app: App, row_id: str) -> bool:
    # While the Commander edits, the row holds an Input and no Label
    return (
        len(app.screen.query(f"#{row_id} .entry-value")) == 1
        and len(app.screen.query(f"#{row_id} Input")) == 0
    )


async def click_into_the_field(edceleste, pilot: Pilot, row_id: str):
    await pilot.click(f"#{row_id}")
    await edceleste.wait_until(
        pilot,
        lambda: isinstance(pilot.app.focused, Input),
        "the field focused for typing",
    )


async def click_in_the_sections_list(pilot: Pilot, section_id: str):
    await pilot.click(f"#settings-sections-column #{section_id}")


@allure.title(
    "Clicking into the API key or the Base URL and leaving it unchanged keeps "
    "the models and the Connected result"
)
@pytest.mark.parametrize(
    "field_name, row_id",
    [("API key", API_KEY_ROW), ("Base URL", BASE_URL_ROW)],
)
@pytest.mark.parametrize("way_out", ["clicks elsewhere", "presses Enter"])
async def test_should_keep_models_and_connected_result_when_a_field_is_left_unchanged(
    edceleste, field_name, row_id, way_out
):
    edceleste.settings.llm.provider.api_key = "old-key"
    edceleste.settings.llm.provider.base_url = "https://llm.example.test/v1"
    edceleste.save_config()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > LLM"):
            await open_settings_section(edceleste, pilot, "settings-llm")
            await edceleste.wait_until(
                pilot, lambda: model_list_is_shown(pilot.app), "the list of LLM models"
            )

        with allure.step("And Test connection shows Connected"):
            await edceleste.click_when_ready(pilot, "#test-connection-button")
            await edceleste.wait_until(
                pilot, lambda: connection_result(pilot.app) == CONNECTED, "Connected"
            )

        with allure.step("And the list of models was loaded when Settings opened"):
            requests_before = edceleste.model_list_requests

        with allure.step(
            f"When the Commander clicks into the {field_name} field, types "
            f"nothing and {way_out}"
        ):
            await click_into_the_field(edceleste, pilot, row_id)
            if way_out == "presses Enter":
                await pilot.press("enter")
            else:
                await click_in_the_sections_list(pilot, "settings-llm")
            await edceleste.wait_until(
                pilot,
                lambda: row_is_a_text_again(pilot.app, row_id),
                "the field closed again",
            )
            # Lets a reload that nobody asked for start, if the app wanted one
            await pilot.pause()

        with allure.step("Then the list of models is not loaded again"):
            assert not model_list_is_loading(pilot.app)
            assert model_list_is_shown(pilot.app)
            assert edceleste.model_list_requests == requests_before

        with allure.step("And Test connection still shows Connected"):
            assert connection_result(pilot.app) == CONNECTED


@allure.title(
    "A different API key loads the models again and wipes the Connected result"
)
async def test_should_reload_models_and_wipe_connected_result_when_the_api_key_changes(
    edceleste,
):
    edceleste.settings.llm.provider.api_key = "old-key"
    edceleste.save_config()

    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > LLM"):
            await open_settings_section(edceleste, pilot, "settings-llm")
            await edceleste.wait_until(
                pilot, lambda: model_list_is_shown(pilot.app), "the list of LLM models"
            )

        with allure.step("And Test connection shows Connected"):
            await edceleste.click_when_ready(pilot, "#test-connection-button")
            await edceleste.wait_until(
                pilot, lambda: connection_result(pilot.app) == CONNECTED, "Connected"
            )

        with allure.step("And the list of models was loaded when Settings opened"):
            requests_before = edceleste.model_list_requests

        with allure.step("When the Commander types another API key and presses Enter"):
            await click_into_the_field(edceleste, pilot, API_KEY_ROW)
            await pilot.press("end", "x", "enter")

        with allure.step("Then the list of models is asked for again and shown"):
            await edceleste.wait_until(
                pilot,
                lambda: edceleste.model_list_requests == requests_before + 1,
                "a new request for the list of models",
            )
            await edceleste.wait_until(
                pilot, lambda: model_list_is_shown(pilot.app), "the list of LLM models"
            )

        with allure.step("And the Connected result is gone"):
            assert connection_result(pilot.app) == ""


@allure.title("Clicking into the journal path and leaving it unchanged shows no change")
async def test_should_not_show_a_change_when_the_journal_path_is_left_unchanged(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens Settings > Paths"):
            await open_settings_section(edceleste, pilot, "settings-paths")

        with allure.step("When the Commander clicks into the journal path and away"):
            await click_into_the_field(edceleste, pilot, JOURNAL_PATH_ROW)
            await click_in_the_sections_list(pilot, "settings-paths")
            await edceleste.wait_until(
                pilot,
                lambda: row_is_a_text_again(pilot.app, JOURNAL_PATH_ROW),
                "the journal path closed again",
            )
            await pilot.pause()

        with allure.step("Then the journal path is not shown in yellow"):
            assert path_is_shown_without_yellow(pilot.app, JOURNAL_PATH_ROW)

        with allure.step("And the Paths section is not marked as changed"):
            assert not section_shows_modified_indicator(pilot.app, "settings-paths")
            assert save_state_text(pilot.app) == ""
