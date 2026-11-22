import allure
import pytest
from textual.app import App
from textual.widgets import Input, TabbedContent
from textual.widgets._footer import FooterKey

from tests.e2e.conftest import comms_entry_types

pytestmark = [pytest.mark.anyio, allure.feature("Ship log")]

CARDS_BY_KEY = {
    "f1": ("LOG", "ship-log-tab-log"),
    "f2": ("SHIP", "ship-log-tab-ship"),
    "f3": ("ENG", "ship-log-tab-eng"),
    "f4": ("STN", "ship-log-tab-stn"),
    "f5": ("SYS", "ship-log-tab-sys"),
    "f6": ("NAV", "ship-log-tab-nav"),
    "f7": ("LDG", "ship-log-tab-ldg"),
}


def ship_log_is_full_width(app: App) -> bool:
    wide_ship_log = app.screen.query_one("#ship-log-wide")
    ship_log_rail = app.screen.query_one("#ship-log-rail")
    assert wide_ship_log.display != ship_log_rail.display
    return wide_ship_log.display


def visible_ship_log_selector(app: App) -> str:
    return "#ship-log-wide" if ship_log_is_full_width(app) else "#ship-log-rail"


def open_card_id(app: App) -> str:
    """The card the Commander sees, read in the part of the ship log on screen"""
    tabs = app.screen.query_one(
        f"{visible_ship_log_selector(app)} TabbedContent", TabbedContent
    )
    return tabs.active


def no_data_texts_in_open_card(app: App) -> list[str]:
    labels = app.screen.query(
        f"{visible_ship_log_selector(app)} #{open_card_id(app)} .ship-log-no-data"
    )
    return [label.render().plain for label in labels]


def footer_entries(app: App) -> list[tuple[str, str]]:
    return [
        (footer_key.key_display, footer_key.description)
        for footer_key in app.screen.query(FooterKey)
    ]


@allure.title("Keys F1 to F7 open the LOG, SHIP, ENG, STN, SYS, NAV and LDG cards")
async def test_should_open_its_own_card_on_each_of_the_keys_f1_to_f7(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        for key, (card_title, card_id) in CARDS_BY_KEY.items():
            with allure.step(f"When the Commander presses {key.upper()}"):
                await pilot.press(key)

            with allure.step(f"Then the {card_title} card is open"):
                await edceleste.wait_until(
                    pilot,
                    lambda: open_card_id(pilot.app) == card_id,
                    f"the {card_title} card to open",
                )


@allure.title("A card that has no content yet says NO DATA")
async def test_should_say_no_data_on_a_card_without_content(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the Commander presses F3 for the ENG card"):
            await pilot.press("f3")

        with allure.step("Then the ENG card is open"):
            await edceleste.wait_until(
                pilot,
                lambda: open_card_id(pilot.app) == "ship-log-tab-eng",
                "the ENG card to open",
            )

        with allure.step("And the card says NO DATA"):
            assert no_data_texts_in_open_card(pilot.app) == ["NO DATA"]


@allure.title("A card key opens the card in the rail when the ship log sits there")
async def test_should_open_the_card_in_the_rail_when_the_ship_log_sits_in_the_rail(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the ship log sits in the rail"):
            assert not ship_log_is_full_width(pilot.app)

        with allure.step("When the Commander presses F2 for the SHIP card"):
            await pilot.press("f2")

        with allure.step("Then the SHIP card is open"):
            await edceleste.wait_until(
                pilot,
                lambda: open_card_id(pilot.app) == "ship-log-tab-ship",
                "the SHIP card to open",
            )

        with allure.step("And the ship log is still in the rail"):
            assert not ship_log_is_full_width(pilot.app)


@allure.title("A card key opens the card full width when the ship log is expanded")
async def test_should_open_the_card_full_width_when_the_ship_log_is_expanded(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander expanded the ship log with Ctrl+E"):
            await pilot.press("ctrl+e")
            await edceleste.wait_until(
                pilot,
                lambda: ship_log_is_full_width(pilot.app),
                "the ship log to open full width",
            )

        with allure.step("When the Commander presses F2 for the SHIP card"):
            await pilot.press("f2")

        with allure.step("Then the SHIP card is open"):
            await edceleste.wait_until(
                pilot,
                lambda: open_card_id(pilot.app) == "ship-log-tab-ship",
                "the SHIP card to open",
            )

        with allure.step("And the ship log is still full width"):
            assert ship_log_is_full_width(pilot.app)


@allure.title("F4 opens the station card full width and Ctrl+E keeps it")
async def test_should_open_the_station_card_full_width_on_f4_and_keep_it_on_ctrl_e(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the ship log sits in the rail"):
            assert not ship_log_is_full_width(pilot.app)

        with allure.step("When the Commander presses F4"):
            await pilot.press("f4")

        with allure.step("Then the station card opens full width"):
            await edceleste.wait_until(
                pilot,
                lambda: ship_log_is_full_width(pilot.app),
                "the ship log to open full width",
            )
            assert open_card_id(pilot.app) == "ship-log-tab-stn"

        with allure.step("When the Commander presses Ctrl+E"):
            await pilot.press("ctrl+e")
            await pilot.pause()

        with allure.step("Then the ship log stays full width on the station card"):
            assert ship_log_is_full_width(pilot.app)
            assert open_card_id(pilot.app) == "ship-log-tab-stn"


@allure.title("A card key does not take the focus or the typed text from COMMS")
async def test_should_keep_the_focus_and_the_typed_text_in_comms_on_a_card_key(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("And the Commander typed hello cel in the COMMS input"):
            await pilot.click("#comms-input")
            await pilot.press(*"hello cel")
            comms_input = pilot.app.screen.query_one("#comms-input", Input)
            assert comms_input.value == "hello cel"

        with allure.step("When the Commander presses F5 for the SYS card"):
            await pilot.press("f5")

        with allure.step("Then the SYS card is open"):
            await edceleste.wait_until(
                pilot,
                lambda: open_card_id(pilot.app) == "ship-log-tab-sys",
                "the SYS card to open",
            )

        with allure.step("And the cursor is still in the COMMS input"):
            assert pilot.app.screen.focused is comms_input

        with allure.step("And the Commander keeps typing and the text is whole"):
            await pilot.press(*"este")
            assert comms_input.value == "hello celeste"

        with allure.step("And nothing was sent to Celeste"):
            assert "user-command" not in comms_entry_types(pilot.app)


@allure.title("The footer shows one entry for all the card keys")
async def test_should_show_one_cards_entry_in_the_footer_for_keys_f1_to_f7(
    edceleste,
):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the Commander looks at the footer"):
            entries = footer_entries(pilot.app)

        with allure.step("Then it shows one entry, f1-f7 Cards"):
            card_entries = [entry for entry in entries if entry[1] == "Cards"]
            assert card_entries == [("f1–f7", "Cards")]

        with allure.step("And no other F key has an entry of its own"):
            assert [key for key, _ in entries if key.startswith("f")] == ["f1–f7"]

        with allure.step("And the Ctrl+E entry is still there"):
            assert ("^e", "Expand log") in entries
