import math
from collections.abc import Callable
from enum import StrEnum
from typing import Any

import httpx
from pydantic_ai import ToolReturn
from edceleste.adapters.tools.tool_register import ToolRegister as tr
from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.services.settings_service import SettingsService

BASE_URL = "https://www.edsm.net"


class EdsmEndpoint(StrEnum):
    SYSTEM_BASE_URL = f"{BASE_URL}/api-system-v1"
    SYSTEM = f"{BASE_URL}/api-v1/system"


USER_AGENT = "Elite Dangerous MCP"
TIMEOUT = 10


class EdsmTools:
    def __init__(
        self,
        client_factory: Callable[[], httpx.AsyncClient],
        settings_service: SettingsService,
        game_state_protocol: GameStateProtocol,
    ):
        """Only stores the dependencies. The external_apis switch is read on
        every call, so turning it off works without a reload."""
        self.client_factory = client_factory
        self.settings_service = settings_service
        self.game_state_protocol = game_state_protocol
        self.system_cache: dict[str, dict[str, Any]] = {}

    async def _base_request_spec(self, url: str, name: str, **params) -> dict[str, Any]:
        """One GET to EDSM with only the system name and the flags. Raises
        httpx errors (timeout, no network, error status) and ValueError for an
        unreadable answer or an empty one, which is how EDSM says "unknown
        system"."""
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

    # pydantic_ai sends the docstring below to the LLM as the tool description,
    # so it is written for the LLM, not for us. How it works: switch off,
    # unknown current system, unknown system name, no answer in time and an
    # error code from EDSM all come back as a ToolReturn with is_error=True, so
    # the LLM can tell the pilot. A raised exception would end the whole LLM
    # turn. An empty from_system means the system the pilot is in now.
    @tr.register_tool(
        name="get_distance",
        readable_name="Get Distance",
        param_name="from_system, to_system",
    )
    async def get_distance(self, from_system: str, to_system: str) -> ToolReturn:
        """Get the distance in light years between two Elite Dangerous star
        systems, given by their exact names. Leave from_system empty to measure
        from the system the pilot is in now. Not for the pilot's jump range or
        position, which are already known."""
        if not self.settings_service.get_settings().external_apis.enabled:
            return self._error("Outside lookups are disabled by the user.")

        if not from_system:
            from_system = (
                self.game_state_protocol.get_game_stats().navigation.current_star_system
            )
            if not from_system:
                return self._error(
                    "The current system is not known yet, so the distance "
                    "cannot be measured from it."
                )

        try:
            from_data = await self.get_system(from_system)
            to_data = await self.get_system(to_system)
            distance = math.dist(
                self._get_coords(from_data, from_system),
                self._get_coords(to_data, to_system),
            )
        except httpx.TimeoutException:
            return self._error("EDSM did not answer in time.")
        except httpx.HTTPStatusError as e:
            return self._error(
                f"EDSM answered with an error code: {e.response.status_code}."
            )
        except httpx.HTTPError:
            return self._error("EDSM did not answer.")
        except ValueError as e:
            return self._error(str(e))

        return ToolReturn(
            return_value={
                "from_system": from_data["name"],
                "to_system": to_data["name"],
                "distance_ly": round(distance, 2),
            },
            metadata={"is_error": False},
        )

    async def get_system(self, name: str) -> dict[str, Any]:
        if name in self.system_cache:
            return self.system_cache[name]
        system = await self._base_request_spec(
            EdsmEndpoint.SYSTEM, name, showCoordinates=1, showInformation=1
        )
        self.system_cache[name] = system
        return system

    @staticmethod
    def _error(text: str) -> ToolReturn:
        return ToolReturn(return_value=text, metadata={"is_error": True})

    @staticmethod
    def _get_coords(system: dict[str, Any], name: str) -> tuple[float, float, float]:
        coords = system.get("coords")
        if not coords:
            raise ValueError(f"System '{name}' has no known coordinates")
        return coords["x"], coords["y"], coords["z"]
