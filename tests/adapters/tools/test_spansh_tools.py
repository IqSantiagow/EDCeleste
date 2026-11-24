import json
import unittest
from typing import Any
from unittest.mock import Mock

import httpx

from edceleste.adapters.tools.spansh_tools import SpanshTools
from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.services.models.settings_model import ExternalApisModel, SettingsModel
from edceleste.services.settings_service import SettingsService
from tests.use_cases.dashboard.game_stats_fixtures import (
    make_game_stats_snapshot,
    make_navigation_stats,
)


def make_station(
    name: str,
    system_name: str = "Sirius",
    distance: float = 10.0,
    distance_to_arrival: float | None = 500.0,
    station_type: str = "Coriolis Starport",
    **extra: Any,
) -> dict[str, Any]:
    """A station as the Spansh station search lists it, with the fields the tool
    reads plus a few it must ignore."""
    return {
        "name": name,
        "system_name": system_name,
        "distance": distance,
        "distance_to_arrival": distance_to_arrival,
        "type": station_type,
        "has_market": True,
        "services": [{"name": "Repair"}],
        **extra,
    }


class TestSpanshTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.found_stations: list[dict[str, Any]] = [make_station("Near Port")]
        self.unknown_systems: set[str] = set()
        self.reference_spellings: dict[str, str] = {}
        self.sent_requests: list[httpx.Request] = []
        self.clients: list[httpx.AsyncClient] = []
        self.transport_error: Exception | None = None
        self.error_status_code: int | None = None
        self.answer_text: str | None = None
        self.external_apis_enabled = True
        self.current_star_system = "Sol"

        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.side_effect = lambda: Mock(
            spec=SettingsModel,
            external_apis=ExternalApisModel(enabled=self.external_apis_enabled),
        )
        self.game_state_protocol = Mock(spec=GameStateProtocol)
        self.game_state_protocol.get_game_stats.side_effect = lambda: (
            make_game_stats_snapshot(
                navigation=make_navigation_stats(
                    current_star_system=self.current_star_system
                )
            )
        )
        self.tools = SpanshTools(
            self.make_client,
            settings_service=self.settings_service,
            game_state_protocol=self.game_state_protocol,
        )

    def respond(self, request: httpx.Request) -> httpx.Response:
        """Answers like Spansh: the stations the test gave, HTTP 400 for a
        system it does not know, or the trouble the test switched on."""
        if self.transport_error is not None:
            raise self.transport_error
        self.sent_requests.append(request)
        if self.error_status_code is not None:
            return httpx.Response(self.error_status_code)
        if self.answer_text is not None:
            return httpx.Response(200, text=self.answer_text)
        reference_system = json.loads(request.content)["reference_system"]
        if reference_system in self.unknown_systems:
            return httpx.Response(400, json={"error": "Invalid request"})
        spelled_name = self.reference_spellings.get(reference_system, reference_system)
        return httpx.Response(
            200,
            json={
                "count": len(self.found_stations),
                "reference": {"name": spelled_name},
                "results": self.found_stations,
            },
        )

    def make_client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.respond))
        self.clients.append(client)
        return client

    def sent_body(self) -> dict[str, Any]:
        """The JSON body of the one request the tool sent."""
        self.assertEqual(len(self.sent_requests), 1)
        return json.loads(self.sent_requests[0].content)

    async def test_should_return_short_station_fields_with_rounded_distances(self):
        self.found_stations = [
            make_station(
                "Patterson Enterprise",
                "Sirius",
                distance=8.58874854460765,
                distance_to_arrival=953.534194,
            )
        ]

        result = await self.tools.find_stations("Sol")

        self.assertFalse(result.metadata["is_error"])
        self.assertEqual(
            result.return_value,
            {
                "from_system": "Sol",
                "stations": [
                    {
                        "name": "Patterson Enterprise",
                        "system": "Sirius",
                        "distance_ly": 8.59,
                        "distance_from_arrival_ls": 954,
                        "type": "Coriolis Starport",
                    }
                ],
            },
        )

    async def test_should_answer_zero_ls_when_spansh_does_not_know_the_arrival_distance(
        self,
    ):
        self.found_stations = [make_station("Odd Port", distance_to_arrival=None)]

        result = await self.tools.find_stations("Sol")

        self.assertEqual(
            result.return_value["stations"][0]["distance_from_arrival_ls"], 0
        )

    async def test_should_add_material_trader_kind_only_for_stations_that_have_one(
        self,
    ):
        self.found_stations = [
            make_station("Trader Port", material_trader="Manufactured"),
            make_station("Plain Port"),
            make_station("Empty Trader Port", material_trader=None),
        ]

        result = await self.tools.find_stations("Sol")

        stations = result.return_value["stations"]
        self.assertEqual(stations[0]["material_trader_kind"], "Manufactured")
        self.assertNotIn("material_trader_kind", stations[1])
        self.assertNotIn("material_trader_kind", stations[2])

    async def test_should_show_at_most_five_stations_nearest_first(self):
        self.found_stations = [
            make_station(f"Port {number}", distance=float(number))
            for number in range(1, 9)
        ]

        result = await self.tools.find_stations("Sol")

        shown_names = [station["name"] for station in result.return_value["stations"]]
        self.assertEqual(shown_names, [f"Port {number}" for number in range(1, 6)])

    async def test_should_drop_stations_in_the_test_system(self):
        self.found_stations = [
            make_station("Junk Port", system_name="Test"),
            make_station("Other Junk Port", system_name="TEST"),
            *[make_station(f"Real Port {number}") for number in range(1, 6)],
        ]

        result = await self.tools.find_stations("Sol")

        shown_names = [station["name"] for station in result.return_value["stations"]]
        self.assertEqual(shown_names, [f"Real Port {number}" for number in range(1, 6)])

    async def test_should_return_empty_list_without_error_when_nothing_found(self):
        self.found_stations = []

        result = await self.tools.find_stations("Sol", 5, ["Technology Broker"])

        self.assertFalse(result.metadata["is_error"])
        self.assertEqual(result.return_value["stations"], [])

    async def test_should_answer_with_the_system_name_as_spansh_spells_it(self):
        self.reference_spellings = {"colonia": "Colonia"}

        result = await self.tools.find_stations("colonia")

        self.assertEqual(result.return_value["from_system"], "Colonia")

    async def test_should_send_only_system_radius_and_service_names(self):
        await self.tools.find_stations("Sol", 20, ["Repair"])

        body = self.sent_body()
        self.assertEqual(
            set(body), {"filters", "sort", "size", "page", "reference_system"}
        )
        self.assertEqual(set(body["filters"]), {"distance", "type", "services"})
        self.assertEqual(body["reference_system"], "Sol")
        self.assertEqual(self.sent_requests[0].headers["User-Agent"], "EDCeleste")

    async def test_should_send_the_radius_as_text_starting_at_zero(self):
        await self.tools.find_stations("Sol", 20)

        self.assertEqual(
            self.sent_body()["filters"]["distance"], {"min": "0", "max": "20"}
        )

    async def test_should_search_fifty_light_years_around_when_no_radius_given(self):
        await self.tools.find_stations("Sol")

        self.assertEqual(self.sent_body()["filters"]["distance"]["max"], "50")

    async def test_should_send_one_filter_entry_per_service(self):
        await self.tools.find_stations("Sol", 50, ["Repair", "Refuel"])

        self.assertEqual(
            self.sent_body()["filters"]["services"],
            [{"name": "Repair"}, {"name": "Refuel"}],
        )

    async def test_should_leave_services_out_of_the_request_when_none_given(self):
        await self.tools.find_stations("Sol")

        self.assertNotIn("services", self.sent_body()["filters"])

    async def test_should_leave_services_out_of_the_request_when_the_list_is_empty(
        self,
    ):
        await self.tools.find_stations("Sol", 50, [])

        self.assertNotIn("services", self.sent_body()["filters"])

    async def test_should_ask_spansh_to_leave_fleet_carriers_out(self):
        await self.tools.find_stations("Sol")

        self.assertEqual(
            self.sent_body()["filters"]["type"],
            {"value": ["Drake-Class Carrier"], "logic": "NOT"},
        )

    async def test_should_ask_spansh_for_the_nearest_stations_first(self):
        await self.tools.find_stations("Sol")

        self.assertEqual(self.sent_body()["sort"], [{"distance": {"direction": "asc"}}])

    async def test_should_search_around_the_current_system_when_from_system_is_empty(
        self,
    ):
        self.current_star_system = "Alpha Centauri"

        result = await self.tools.find_stations("")

        self.assertEqual(self.sent_body()["reference_system"], "Alpha Centauri")
        self.assertEqual(result.return_value["from_system"], "Alpha Centauri")

    async def test_should_return_error_without_request_when_current_system_is_unknown(
        self,
    ):
        self.current_star_system = ""

        result = await self.tools.find_stations("")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("current system", result.return_value)
        self.assertEqual(self.sent_requests, [])

    async def test_should_spell_service_names_like_spansh_ignoring_case(self):
        await self.tools.find_stations("Sol", 50, ["material trader", "REPAIR"])

        self.assertEqual(
            self.sent_body()["filters"]["services"],
            [{"name": "Material Trader"}, {"name": "Repair"}],
        )

    async def test_should_suggest_closest_names_for_an_unknown_service(self):
        result = await self.tools.find_stations("Sol", 50, ["Interstellar Factors"])

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("'Interstellar Factors'", result.return_value)
        self.assertIn("closest: Interstellar Factors Contact", result.return_value)
        self.assertEqual(self.sent_requests, [])

    async def test_should_list_known_services_when_nothing_is_close(self):
        result = await self.tools.find_stations("Sol", 50, ["xyzzy"])

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("'xyzzy'", result.return_value)
        self.assertNotIn("closest", result.return_value)
        self.assertIn("Known services:", result.return_value)
        self.assertIn("Technology Broker", result.return_value)
        self.assertEqual(self.sent_requests, [])

    async def test_should_report_every_unknown_service_when_several_are_wrong(self):
        result = await self.tools.find_stations(
            "Sol", 50, ["Interstellar Factors", "Repair", "xyzzy"]
        )

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("'Interstellar Factors'", result.return_value)
        self.assertIn("'xyzzy'", result.return_value)
        self.assertNotIn("'Repair'", result.return_value)

    async def test_should_name_the_system_when_spansh_answers_400(self):
        self.unknown_systems = {"Nowhere"}

        result = await self.tools.find_stations("Nowhere")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(result.return_value, "System 'Nowhere' not found")

    async def test_should_return_error_with_status_code_when_spansh_answers_500(self):
        self.error_status_code = 500

        result = await self.tools.find_stations("Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(
            result.return_value, "Spansh answered with an error code: 500."
        )

    async def test_should_return_error_when_spansh_does_not_answer_in_time(self):
        self.transport_error = httpx.ReadTimeout("too slow")

        result = await self.tools.find_stations("Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(result.return_value, "Spansh did not answer in time.")

    async def test_should_return_error_when_the_network_is_down(self):
        self.transport_error = httpx.ConnectError("no network")

        result = await self.tools.find_stations("Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(result.return_value, "Spansh did not answer.")

    async def test_should_return_error_when_the_answer_is_not_json(self):
        self.answer_text = "<html>maintenance</html>"

        result = await self.tools.find_stations("Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(result.return_value, "Spansh returned an invalid response")

    async def test_should_return_error_and_make_no_request_when_switch_is_off(self):
        self.external_apis_enabled = False

        result = await self.tools.find_stations("Sol", 50, ["Repair"])

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(
            result.return_value, "Outside lookups are disabled by the user."
        )
        self.assertEqual(self.clients, [])
        self.assertEqual(self.sent_requests, [])

    async def test_should_close_the_http_client_after_each_request(self):
        await self.tools.find_stations("Sol")
        await self.tools.find_stations("Sol")

        self.assertEqual(len(self.clients), 2)
        self.assertTrue(all(client.is_closed for client in self.clients))


if __name__ == "__main__":
    unittest.main()
