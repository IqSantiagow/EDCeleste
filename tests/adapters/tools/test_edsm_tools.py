import unittest

import httpx

from edceleste.adapters.tools.edsm_tools import EdsmTools


class TestEdsmTools(unittest.IsolatedAsyncioTestCase):
    async def test_should_close_http_clients_after_requests(self):
        requests = []
        clients = []
        coordinates = {
            "Sol": {"x": 0, "y": 0, "z": 0},
            "Alpha": {"x": 3, "y": 4, "z": 0},
            "Beta": {"x": 0, "y": 0, "z": 12},
        }

        def respond(request: httpx.Request) -> httpx.Response:
            name = request.url.params["systemName"]
            requests.append(name)
            return httpx.Response(200, json={"coords": coordinates[name]})

        def client_factory() -> httpx.AsyncClient:
            client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            clients.append(client)
            return client

        tools = EdsmTools(client_factory)

        first_distance = await tools.get_distance("Sol", "Alpha")
        second_distance = await tools.get_distance("Alpha", "Beta")

        self.assertEqual(first_distance.return_value, 5)
        self.assertEqual(second_distance.return_value, 13)
        self.assertEqual(len(clients), 3)
        self.assertTrue(all(client.is_closed for client in clients))
        self.assertEqual(requests, ["Sol", "Alpha", "Beta"])


if __name__ == "__main__":
    unittest.main()
