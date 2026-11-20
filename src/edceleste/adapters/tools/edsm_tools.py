import math
from collections.abc import Callable
from enum import StrEnum
from typing import Any

import httpx
from pydantic_ai import ToolReturn
from edceleste.adapters.tools.tool_register import ToolRegister as tr

BASE_URL = "https://www.edsm.net"


class EdsmEndpoint(StrEnum):
    SYSTEM_BASE_URL = f"{BASE_URL}/api-system-v1"
    SYSTEM = f"{BASE_URL}/api-v1/system"


USER_AGENT = "Elite Dangerous MCP"
TIMEOUT = 10


class EdsmTools:
    def __init__(self, client_factory: Callable[[], httpx.AsyncClient]):
        self.client_factory = client_factory
        self.system_cache: dict[str, dict[str, Any]] = {}

    async def _base_request_spec(self, url: str, name: str, **params) -> dict[str, Any]:
        async with self.client_factory() as client:
            response = await client.get(
                url,
                params={"systemName": name, **params},
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )

        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as e:
            raise ValueError(f"EDSM returned an invalid response for '{name}'") from e

        if not data:
            raise ValueError(f"System '{name}' not found")

        return data

    @tr.register_tool(
        name="get_distance", readable_name="Get Distance", param_name="system1, system2"
    )
    async def get_distance(self, system1: str, system2: str) -> ToolReturn:
        """Get the distance in light years between two Elite Dangerous star
        systems, given by their exact names. Fails if EDSM does not know a
        system or its coordinates."""
        distance = math.dist(
            await self._get_coords(system1), await self._get_coords(system2)
        )
        return ToolReturn(return_value=distance)

    async def get_system(self, name: str) -> dict[str, Any]:
        if name in self.system_cache:
            return self.system_cache[name]
        system = await self._base_request_spec(
            EdsmEndpoint.SYSTEM, name, showCoordinates=1, showInformation=1
        )
        self.system_cache[name] = system
        return system

    async def _get_coords(self, name: str) -> tuple[float, float, float]:
        coords = (await self.get_system(name)).get("coords")
        if not coords:
            raise ValueError(f"System '{name}' has no known coordinates")
        return coords["x"], coords["y"], coords["z"]
