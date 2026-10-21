import allure
import pytest
from textual.pilot import Pilot
from textual.widgets import Label

from edceleste.ui.screens.settings.settings_screen import SettingsScreen
from tests.e2e.conftest import (
    click_bind_and_wait_for_the_dialog,
    key_shown_in_the_dialog,
    open_stt_settings,
)
from tests.e2e.test_settings import save_state_text

pytestmark = [pytest.mark.anyio, allure.feature("Push-to-talk key")]

KEY_THE_GAME_USES = "'l'"
PROMPT = "Press a key or a mouse button..."


def dialog_text(app, label_id: str) -> str | None:
    labels = app.screen.query(f"#{label_id}")
    if len(labels) != 1:
        return None
    return str(labels.first().content)


def confirm_is_disabled(app) -> bool:
    return app.screen.query_one("#bind-hotkey-confirm-button").disabled


async def open_the_dialog(edceleste, pilot: Pilot) -> None:
    await open_stt_settings(edceleste, pilot)
    await click_bind_and_wait_for_the_dialog(edceleste, pilot)


async def wait_for_the_key_in_the_dialog(edceleste, pilot: Pilot, key_name: str):
    await edceleste.wait_until(
        pilot,
        lambda: key_shown_in_the_dialog(pilot.app) == key_name,
        f"{key_name} shown in the dialog",
    )


@allure.title("The dialog refuses a key the game already uses")
async def test_should_refuse_a_key_the_game_already_uses(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens the BIND HOTKEY dialog"):
            await open_the_dialog(edceleste, pilot)

        with allure.step("When the Commander presses L, which the game uses"):
            await edceleste.global_keys_and_mouse.hold_key(KEY_THE_GAME_USES)
            await wait_for_the_key_in_the_dialog(edceleste, pilot, KEY_THE_GAME_USES)

        with allure.step("Then the dialog says the key is already used in the game"):
            error_text = dialog_text(pilot.app, "bind-hotkey-error")
            assert error_text is not None
            assert error_text.startswith("✗ Already used in the game: ")

        with allure.step("And CONFIRM is disabled"):
            assert confirm_is_disabled(pilot.app)


@allure.title("RETRY lets the Commander choose another key and then confirm it")
async def test_should_let_the_commander_try_again_after_a_refused_key(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens the BIND HOTKEY dialog"):
            await open_the_dialog(edceleste, pilot)

        with allure.step("And the Commander pressed L, which the game uses"):
            await edceleste.global_keys_and_mouse.hold_key(KEY_THE_GAME_USES)
            await wait_for_the_key_in_the_dialog(edceleste, pilot, KEY_THE_GAME_USES)

        with allure.step("And the Commander clicked RETRY"):
            await edceleste.click_when_ready(pilot, "#bind-hotkey-retry-button")
            await edceleste.wait_until(
                pilot,
                lambda: dialog_text(pilot.app, "bind-hotkey-prompt") == PROMPT,
                "the dialog asking for a key again",
            )

        with allure.step("When the Commander presses F9"):
            await edceleste.global_keys_and_mouse.hold_key("Key.f9")
            await wait_for_the_key_in_the_dialog(edceleste, pilot, "Key.f9")

        with allure.step("Then the error is gone and CONFIRM is enabled"):
            assert dialog_text(pilot.app, "bind-hotkey-error") is None
            assert not confirm_is_disabled(pilot.app)


@allure.title("CONFIRM stays disabled until a key is caught")
async def test_should_keep_confirm_disabled_until_a_key_is_caught(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander is in Settings > Speech to text"):
            await open_stt_settings(edceleste, pilot)

        with allure.step("When the Commander clicks BIND"):
            await click_bind_and_wait_for_the_dialog(edceleste, pilot)

        with allure.step("Then the dialog asks for a key or a mouse button"):
            assert dialog_text(pilot.app, "bind-hotkey-prompt") == PROMPT

        with allure.step("And CONFIRM is disabled"):
            assert confirm_is_disabled(pilot.app)


@allure.title("Cancelling the dialog keeps the push-to-talk key as it was")
async def test_should_keep_the_key_when_the_dialog_is_cancelled(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens the BIND HOTKEY dialog"):
            await open_the_dialog(edceleste, pilot)

        with allure.step("And the Commander pressed F9"):
            await edceleste.global_keys_and_mouse.hold_key("Key.f9")
            await wait_for_the_key_in_the_dialog(edceleste, pilot, "Key.f9")

        with allure.step("When the Commander clicks CANCEL"):
            await edceleste.click_when_ready(pilot, "#bind-hotkey-cancel-button")
            await edceleste.wait_until(
                pilot,
                lambda: isinstance(pilot.app.screen, SettingsScreen),
                "the settings screen after the dialog closes",
            )

        with allure.step("Then the row still shows None and nothing is MODIFIED"):
            row_value = pilot.app.screen.query_one("#hotkey-value-label", Label)
            assert str(row_value.content) == "None"
            assert save_state_text(pilot.app) == ""


@allure.title("Only the side buttons of the mouse can be the push-to-talk key")
async def test_should_ignore_the_main_mouse_buttons_and_catch_a_side_button(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander opens the BIND HOTKEY dialog"):
            await open_the_dialog(edceleste, pilot)

        with allure.step(
            "When the Commander clicks the left, right and middle mouse buttons "
            "and then the side button"
        ):
            for button_name in ("left", "right", "middle", "x1"):
                await edceleste.global_keys_and_mouse.click_mouse_button(button_name)

        with allure.step("Then the dialog shows the side button"):
            await wait_for_the_key_in_the_dialog(edceleste, pilot, "Button.x1")
