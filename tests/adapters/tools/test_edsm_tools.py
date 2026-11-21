import unittest
from unittest.mock import Mock

import httpx

from edceleste.adapters.tools.edsm_tools import EdsmTools
from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.services.models.settings_model import ExternalApisModel, SettingsModel
from edceleste.services.settings_service import SettingsService
from tests.use_cases.dashboard.game_stats_fixtures import (
    make_game_stats_snapshot,
    make_navigation_stats,
)

SOL_COORDINATES = {"x": 0, "y": 0, "z": 0}
COLONIA_COORDINATES = {"x": -9530.5, "y": -910.28125, "z": 19808.125}


def make_station(name: str, distance: float, station_type="Orbis Starport", **extra):
    """A station as the EDSM stations endpoint lists it."""
    return {
        "name": name,
        "type": station_type,
        "distanceToArrival": distance,
        "haveMarket": True,
        "haveShipyard": False,
        "haveOutfitting": True,
        "otherServices": ["Refuel", "Repair"],
        **extra,
    }


class TestEdsmTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.known_systems = {
            "Sol": {
                "name": "Sol",
                "coords": SOL_COORDINATES,
                "requirePermit": True,
                "permitName": "Sol",
                "information": {
                    "allegiance": "Federation",
                    "government": "Democracy",
                    "faction": "Mother Gaia",
                    "population": 18320926115,
                    "security": "High",
                    "economy": "Refinery",
                    "secondEconomy": "Service",
                },
            },
            "Colonia": {"name": "Colonia", "coords": COLONIA_COORDINATES},
            "Alpha": {"name": "Alpha", "coords": {"x": 3, "y": 4, "z": 0}},
            "Beta": {"name": "Beta", "coords": {"x": 0, "y": 0, "z": 12}},
            "Empty": {
                "name": "Empty",
                "coords": {"x": 1, "y": 1, "z": 1},
                "requirePermit": False,
                "information": {},
            },
        }
        self.known_stations = {
            "Sol": {"name": "Sol", "stations": [make_station("Far Port", 900)]},
            "Empty": {"name": "Empty", "stations": []},
        }
        self.requested_names: list[str] = []
        self.clients: list[httpx.AsyncClient] = []
        self.transport_error: Exception | None = None
        self.error_status_code: int | None = None
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
        self.tools = EdsmTools(
            self.make_client,
            settings_service=self.settings_service,
            game_state_protocol=self.game_state_protocol,
        )

    def respond(self, request: httpx.Request) -> httpx.Response:
        if self.transport_error is not None:
            raise self.transport_error
        if self.error_status_code is not None:
            return httpx.Response(self.error_status_code)
        name = request.url.params["systemName"]
        self.requested_names.append(name)
        # EDSM answers [] (system) or {} (stations) with HTTP 200 for an unknown name
        if request.url.path.endswith("/stations"):
            return httpx.Response(200, json=self.known_stations.get(name, {}))
        return httpx.Response(200, json=self.known_systems.get(name, []))

    def make_client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.respond))
        self.clients.append(client)
        return client

    async def test_should_close_http_clients_after_requests(self):
        await self.tools.get_distance("Sol", "Alpha")
        await self.tools.get_distance("Alpha", "Beta")

        self.assertEqual(len(self.clients), 3)
        self.assertTrue(all(client.is_closed for client in self.clients))
        self.assertEqual(self.requested_names, ["Sol", "Alpha", "Beta"])

    async def test_should_return_both_names_and_distance_rounded_to_two_decimals(
        self,
    ):
        result = await self.tools.get_distance("Sol", "Colonia")

        self.assertEqual(
            result.return_value,
            {"from_system": "Sol", "to_system": "Colonia", "distance_ly": 22000.47},
        )
        self.assertFalse(result.metadata["is_error"])

    async def test_should_return_zero_distance_for_the_same_system_twice(self):
        result = await self.tools.get_distance("Sol", "Sol")

        self.assertEqual(result.return_value["distance_ly"], 0)
        self.assertFalse(result.metadata["is_error"])

    async def test_should_measure_from_current_system_when_from_system_is_empty(self):
        self.current_star_system = "Alpha"

        result = await self.tools.get_distance("", "Beta")

        self.assertEqual(result.return_value["from_system"], "Alpha")
        self.assertEqual(result.return_value["distance_ly"], 13)

    async def test_should_return_error_when_current_system_is_not_known_yet(self):
        self.current_star_system = ""

        result = await self.tools.get_distance("", "Beta")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("current system", result.return_value)
        self.assertEqual(self.requested_names, [])

    async def test_should_return_error_and_make_no_request_when_switch_is_off(self):
        self.external_apis_enabled = False

        result = await self.tools.get_distance("Sol", "Colonia")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(
            result.return_value, "Outside lookups are disabled by the user."
        )
        self.assertEqual(self.clients, [])

    async def test_should_name_the_system_that_edsm_does_not_know(self):
        result = await self.tools.get_distance("Sol", "Nowhere")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("Nowhere", result.return_value)

    async def test_should_name_the_unknown_system_when_it_is_the_first_one(self):
        result = await self.tools.get_distance("Nowhere", "Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("Nowhere", result.return_value)

    async def test_should_return_error_when_edsm_does_not_answer_in_time(self):
        self.transport_error = httpx.ReadTimeout("too slow")

        result = await self.tools.get_distance("Sol", "Colonia")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("did not answer", result.return_value)

    async def test_should_return_error_when_network_is_off(self):
        self.transport_error = httpx.ConnectError("no network")

        result = await self.tools.get_distance("Sol", "Colonia")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("did not answer", result.return_value)

    async def test_should_return_error_with_status_code_when_edsm_answers_with_error(
        self,
    ):
        self.error_status_code = 503

        result = await self.tools.get_distance("Sol", "Colonia")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("503", result.return_value)

    async def test_should_send_only_system_names(self):
        sent_queries: list[dict] = []

        def respond(request: httpx.Request) -> httpx.Response:
            sent_queries.append(dict(request.url.params))
            return httpx.Response(200, json=self.known_systems["Sol"])

        tools = EdsmTools(
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
            settings_service=self.settings_service,
            game_state_protocol=self.game_state_protocol,
        )

        await tools.get_distance("Sol", "Sol")

        self.assertTrue(sent_queries)
        for query in sent_queries:
            self.assertEqual(
                set(query) - {"showCoordinates", "showInformation", "showPermit"},
                {"systemName"},
            )

    async def test_system_info_should_return_the_facts_about_the_system(self):
        result = await self.tools.get_system_info("Sol")

        self.assertFalse(result.metadata["is_error"])
        self.assertEqual(
            result.return_value,
            {
                "name": "Sol",
                "allegiance": "Federation",
                "government": "Democracy",
                "controlling_faction": "Mother Gaia",
                "economy": "Refinery",
                "second_economy": "Service",
                "security": "High",
                "population": 18320926115,
                "requires_permit": True,
                "permit_name": "Sol",
            },
        )

    async def test_system_info_should_not_fail_for_a_system_without_information(self):
        result = await self.tools.get_system_info("Empty")

        self.assertFalse(result.metadata["is_error"])
        self.assertIsNone(result.return_value["economy"])
        self.assertFalse(result.return_value["requires_permit"])

    async def test_system_info_should_use_current_system_when_name_is_empty(self):
        self.current_star_system = "Sol"

        result = await self.tools.get_system_info("")

        self.assertEqual(result.return_value["name"], "Sol")

    async def test_system_info_should_say_the_system_is_unknown(self):
        result = await self.tools.get_system_info("Nowhere")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("Nowhere", result.return_value)

    async def test_system_info_should_make_no_request_when_switch_is_off(self):
        self.external_apis_enabled = False

        result = await self.tools.get_system_info("Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(self.clients, [])

    async def test_system_info_should_return_error_when_edsm_does_not_answer(self):
        self.transport_error = httpx.ReadTimeout("too slow")

        result = await self.tools.get_system_info("Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("did not answer", result.return_value)

    async def test_stations_should_list_station_with_type_distance_and_services(self):
        result = await self.tools.get_system_stations("Sol")

        self.assertFalse(result.metadata["is_error"])
        self.assertEqual(result.return_value["system"], "Sol")
        self.assertEqual(
            result.return_value["stations"],
            [
                {
                    "name": "Far Port",
                    "type": "Orbis Starport",
                    "distance_from_arrival_ls": 900,
                    "body": None,
                    "has_market": True,
                    "has_shipyard": False,
                    "has_outfitting": True,
                    "other_services": ["Refuel", "Repair"],
                }
            ],
        )

    async def test_stations_should_name_the_body_of_a_planetary_station(self):
        self.known_stations["Sol"]["stations"] = [
            make_station("Mercury Port", 157, body={"id": 1, "name": "Mercury"})
        ]

        result = await self.tools.get_system_stations("Sol")

        self.assertEqual(result.return_value["stations"][0]["body"], "Mercury")

    async def test_stations_should_answer_no_stations_for_a_system_without_any(self):
        result = await self.tools.get_system_stations("Empty")

        self.assertFalse(result.metadata["is_error"])
        self.assertEqual(result.return_value["stations"], [])
        self.assertEqual(result.return_value["stations_not_shown"], 0)

    async def test_stations_should_say_the_system_is_unknown(self):
        result = await self.tools.get_system_stations("Nowhere")

        self.assertTrue(result.metadata["is_error"])
        self.assertIn("Nowhere", result.return_value)

    async def test_stations_should_use_current_system_when_name_is_empty(self):
        self.current_star_system = "Empty"

        result = await self.tools.get_system_stations("")

        self.assertEqual(result.return_value["system"], "Empty")

    async def test_stations_should_make_no_request_when_switch_is_off(self):
        self.external_apis_enabled = False

        result = await self.tools.get_system_stations("Sol")

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(self.clients, [])

    async def test_stations_should_show_nearest_ten_and_count_the_rest(self):
        self.known_stations["Sol"]["stations"] = [
            make_station(f"Port {distance}", distance) for distance in range(15, 0, -1)
        ]

        result = await self.tools.get_system_stations("Sol")

        shown_names = [station["name"] for station in result.return_value["stations"]]
        self.assertEqual(shown_names, [f"Port {distance}" for distance in range(1, 11)])
        self.assertEqual(result.return_value["stations_not_shown"], 5)

    async def test_stations_should_leave_fleet_carriers_out_and_count_them(self):
        self.known_stations["Sol"]["stations"] = [
            make_station("Real Port", 10),
            make_station("ABC-123", 0, station_type="Fleet Carrier"),
            make_station("DEF-456", 0, station_type="Fleet Carrier"),
        ]

        result = await self.tools.get_system_stations("Sol")

        shown_names = [station["name"] for station in result.return_value["stations"]]
        self.assertEqual(shown_names, ["Real Port"])
        self.assertEqual(result.return_value["fleet_carriers_not_listed"], 2)


if __name__ == "__main__":
    unittest.main()
