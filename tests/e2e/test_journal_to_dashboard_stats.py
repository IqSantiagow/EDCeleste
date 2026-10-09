import allure
import pytest
from textual.app import App
from textual.widgets import Label

from edceleste.ui.screens.app.widgets.widget_common_stat_label import (
    WidgetCommonStatLabel,
)
from tests.e2e.conftest import ship_log_events

pytestmark = [pytest.mark.anyio, allure.feature("Dashboard stats from the game")]


def label_text(app: App, selector: str) -> str:
    return str(app.screen.query_one(selector, Label).content)


def header_value(app: App, selector: str) -> str:
    return app.screen.query_one(selector, WidgetCommonStatLabel).stat_value


@allure.title("The header shows the Commander, the ship and the credits")
async def test_should_show_the_commander_ship_and_credits_in_the_header(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the game writes Status.json"):
            edceleste.write_status_file()

        with allure.step("Then the header shows SANTIAGOW, Cobra Mk III, 575382 CR"):
            await edceleste.wait_until(
                pilot,
                lambda: header_value(pilot.app, "#stat-cmdr") == "SANTIAGOW",
                "the commander name in the header",
            )
            assert header_value(pilot.app, "#stat-ship") == "Cobra Mk III"
            assert header_value(pilot.app, "#stat-credits") == "575382"


@allure.title("Navigation shows the new star system after a jump")
async def test_should_show_the_new_system_in_navigation_after_a_jump(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        with allure.step("When the game writes FSDJump to Beta Sculptoris"):
            edceleste.append_journal_event("FSDJump")
            await edceleste.wait_until(
                pilot,
                lambda: "FSDJump" in ship_log_events(pilot.app),
                "FSDJump in the ship log before the game writes Status.json",
            )

        with allure.step("And the game writes Status.json"):
            edceleste.write_status_file()

        with allure.step("Then navigation shows Beta Sculptoris"):
            await edceleste.wait_until(
                pilot,
                lambda: (
                    label_text(pilot.app, "#navigation-system") == "Beta Sculptoris"
                ),
                "Beta Sculptoris in navigation",
            )

        with allure.step("And its security, allegiance, economy and population"):
            assert label_text(pilot.app, "#navigation-security") == "● HIGH SECURITY"
            assert label_text(pilot.app, "#navigation-allegiance") == "Independent"
            assert (
                label_text(pilot.app, "#navigation-economy") == "High Tech / Extraction"
            )
            assert label_text(pilot.app, "#navigation-population") == "14 182 335"
