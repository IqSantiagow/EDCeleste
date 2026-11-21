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


class TestEdsmTools(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.known_systems = {
            "Sol": {"name": "Sol", "coords": SOL_COORDINATES},
            "Colonia": {"name": "Colonia", "coords": COLONIA_COORDINATES},
            "Alpha": {"name": "Alpha", "coords": {"x": 3, "y": 4, "z": 0}},
            "Beta": {"name": "Beta", "coords": {"x": 0, "y": 0, "z": 12}},
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
        if name not in self.known_systems:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=self.known_systems[name])

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
                set(query) - {"showCoordinates", "showInformation"}, {"systemName"}
            )


if __name__ == "__main__":
    unittest.main()
