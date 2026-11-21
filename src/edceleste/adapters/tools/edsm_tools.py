import math
from collections.abc import Awaitable, Callable
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
MAX_STATIONS_SHOWN = 10


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

    async def _fetch_edsm_json(
        self, url: str, system_name: str, **query_flags
    ) -> dict[str, Any]:
        """One GET to url (network, no retry, TIMEOUT seconds) that sends only
        systemName=system_name plus query_flags (extra query parameters such as
        showCoordinates=1). Returns the JSON answer as a dict.
        Raises httpx errors (timeout, no network, error status) and ValueError
        for an answer that is not JSON or an empty one ([] or {}), which is how
        EDSM says "unknown system"."""
        async with self.client_factory() as client:
            response = await client.get(
                url,
                params={"systemName": system_name, **query_flags},
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )

        response.raise_for_status()

        try:
            data = response.json()
        except ValueError as e:
            raise ValueError(
                f"EDSM returned an invalid response for '{system_name}'"
            ) from e

        if not data:
            raise ValueError(f"System '{system_name}' not found")

        return data

    async def _run_lookup_if_enabled_or_return_error(
        self, work: Callable[[], Awaitable[dict[str, Any]]]
    ) -> ToolReturn:
        """The part every tool shares. Returns an error ToolReturn without
        calling work (so without any request) when the external_apis switch is
        off. Otherwise awaits work and wraps its dict in a ToolReturn.
        A ValueError from work (unknown system, unreadable answer) and the
        httpx errors (timeout, no network, error status) become an error
        ToolReturn with a sentence for the pilot. A raised exception would end
        the whole LLM turn."""
        if not self.settings_service.get_settings().external_apis.enabled:
            return self._error_tool_return("Outside lookups are disabled by the user.")

        try:
            answer = await work()
        except httpx.TimeoutException:
            return self._error_tool_return("EDSM did not answer in time.")
        except httpx.HTTPStatusError as e:
            return self._error_tool_return(
                f"EDSM answered with an error code: {e.response.status_code}."
            )
        except httpx.HTTPError:
            return self._error_tool_return("EDSM did not answer.")
        except ValueError as e:
            return self._error_tool_return(str(e))

        return ToolReturn(return_value=answer, metadata={"is_error": False})

    def _name_or_current_system(self, system_name: str) -> str:
        """Gives system_name back, or the system the pilot is in now when
        system_name is empty. Raises ValueError when that system is not known
        yet (the game has not written one)."""
        if system_name:
            return system_name
        current_system = (
            self.game_state_protocol.get_game_stats().navigation.current_star_system
        )
        if not current_system:
            raise ValueError("The current system is not known yet.")
        return current_system

    @tr.register_tool(
        name="get_distance",
        readable_name="Get Distance",
        param_name="from_system, to_system",
    )
    async def get_distance(self, from_system: str, to_system: str) -> ToolReturn:
        """Get the distance in light years between two Elite Dangerous star
        systems, given by their exact names. Leave from_system empty to measure
        from the system the pilot is in now. Not for the pilot's jump range or
        position, which are already known.
        Answers with from_system and to_system as EDSM spells them and
        distance_ly rounded to two decimals (0 for the same system twice).
        Answers with an error text when lookups are switched off, the current
        system is not known yet, a system is unknown or has no coordinates, or
        EDSM does not answer."""

        async def measure_distance() -> dict[str, Any]:
            from_name = self._name_or_current_system(from_system)
            from_data = await self._fetch_system_cached(from_name)
            to_data = await self._fetch_system_cached(to_system)
            distance = math.dist(
                self._read_coordinates_or_raise(from_data, from_name),
                self._read_coordinates_or_raise(to_data, to_system),
            )
            return {
                "from_system": from_data["name"],
                "to_system": to_data["name"],
                "distance_ly": round(distance, 2),
            }

        return await self._run_lookup_if_enabled_or_return_error(measure_distance)

    @tr.register_tool(
        name="get_system_info",
        readable_name="Get System Info",
        param_name="system",
    )
    async def get_system_info(self, system: str) -> ToolReturn:
        """Get facts about an Elite Dangerous star system from outside data:
        allegiance, government, controlling faction, economy (and the second
        one), security, population and whether it needs a permit. Use it for
        any system, also the pilot's own. Leave system empty for the system the
        pilot is in now. A field EDSM does not know (for example the economy of
        an uninhabited system) is None, which is not an error. Answers with an
        error text for the same failures as get_distance."""

        async def look_up_system() -> dict[str, Any]:
            system_name = self._name_or_current_system(system)
            system_data = await self._fetch_system_cached(system_name)
            information = system_data.get("information") or {}
            return {
                "name": system_data["name"],
                "allegiance": information.get("allegiance"),
                "government": information.get("government"),
                "controlling_faction": information.get("faction"),
                "economy": information.get("economy"),
                "second_economy": information.get("secondEconomy"),
                "security": information.get("security"),
                "population": information.get("population"),
                "requires_permit": system_data.get("requirePermit", False),
                "permit_name": system_data.get("permitName"),
            }

        return await self._run_lookup_if_enabled_or_return_error(look_up_system)

    @tr.register_tool(
        name="get_system_stations",
        readable_name="Get System Stations",
        param_name="system",
    )
    async def get_system_stations(self, system: str) -> ToolReturn:
        """List the stations of an Elite Dangerous star system, nearest to the
        arrival point first: name, type, distance from the arrival point in
        light seconds, the body for a planetary station, and whether it has a
        market, shipyard, outfitting and which other services. Use it also to
        tell whether a station has a shipyard. Leave system empty for the
        system the pilot is in now.
        Fleet carriers are left out and only counted in fleet_carriers_not_listed.
        At most the 10 nearest stations are listed, the others are counted in
        stations_not_shown. A system without stations answers with an empty
        stations list, which is not an error. Answers with an error text for
        the same failures as get_distance."""

        async def look_up_stations() -> dict[str, Any]:
            system_name = self._name_or_current_system(system)
            stations_data = await self._fetch_edsm_json(
                f"{EdsmEndpoint.SYSTEM_BASE_URL}/stations", system_name
            )
            all_stations = stations_data.get("stations", [])
            stations = [s for s in all_stations if s["type"] != "Fleet Carrier"]
            stations.sort(key=lambda s: s.get("distanceToArrival") or 0)
            return {
                "system": stations_data["name"],
                "stations": [
                    {
                        "name": station["name"],
                        "type": station["type"],
                        "distance_from_arrival_ls": station.get("distanceToArrival"),
                        "body": (station.get("body") or {}).get("name"),
                        "has_market": station.get("haveMarket", False),
                        "has_shipyard": station.get("haveShipyard", False),
                        "has_outfitting": station.get("haveOutfitting", False),
                        "other_services": station.get("otherServices", []),
                    }
                    for station in stations[:MAX_STATIONS_SHOWN]
                ],
                "stations_not_shown": max(len(stations) - MAX_STATIONS_SHOWN, 0),
                "fleet_carriers_not_listed": len(all_stations) - len(stations),
            }

        return await self._run_lookup_if_enabled_or_return_error(look_up_stations)

    async def _fetch_system_cached(self, system_name: str) -> dict[str, Any]:
        """The EDSM entry of one system with coordinates, information and
        permit. Asks EDSM once per name, later calls answer from system_cache.
        Raises like _fetch_edsm_json."""
        if system_name in self.system_cache:
            return self.system_cache[system_name]
        system = await self._fetch_edsm_json(
            EdsmEndpoint.SYSTEM,
            system_name,
            showCoordinates=1,
            showInformation=1,
            showPermit=1,
        )
        self.system_cache[system_name] = system
        return system

    @staticmethod
    def _error_tool_return(text: str) -> ToolReturn:
        """A ToolReturn whose value is text for the pilot and whose metadata
        says is_error=True, so COMMS shows an error and the LLM tells the pilot.
        Nothing is raised, so the LLM turn goes on."""
        return ToolReturn(return_value=text, metadata={"is_error": True})

    @staticmethod
    def _read_coordinates_or_raise(
        system: dict[str, Any], system_name: str
    ) -> tuple[float, float, float]:
        """The (x, y, z) of an EDSM system entry, read from its "coords" key.
        Raises ValueError naming system_name when the entry has no coordinates
        (EDSM does not know them for some systems)."""
        coords = system.get("coords")
        if not coords:
            raise ValueError(f"System '{system_name}' has no known coordinates")
        return coords["x"], coords["y"], coords["z"]
