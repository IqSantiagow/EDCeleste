import difflib
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from pydantic_ai import ToolReturn
from edceleste.adapters.tools.tool_register import ToolRegister as tr
from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.services.settings_service import SettingsService

STATION_SEARCH_URL = "https://spansh.co.uk/api/stations/search"
USER_AGENT = "EDCeleste"
TIMEOUT = 10
MAX_STATIONS_SHOWN = 5
# More than MAX_STATIONS_SHOWN, because junk entries are dropped after the search.
STATIONS_ASKED_FOR = 20
FLEET_CARRIER_TYPE = "Drake-Class Carrier"
# Lower-case names of systems that only hold junk entries. Their stations are
# dropped from the answer.
JUNK_SYSTEM_NAMES = {"test"}

# Spansh service names, from GET /api/stations/field_values/services on 2026-11-24.
KNOWN_SERVICES = [
    "Flight Controller",
    "Station Operations",
    "Dock",
    "Autodock",
    "Station Menu",
    "Contacts",
    "Refuel",
    "Market",
    "Repair",
    "Workshop",
    "Missions",
    "Search and Rescue",
    "Missions Generated",
    "Restock",
    "Social Space",
    "Black Market",
    "Interstellar Factors Contact",
    "System Colonisation",
    "Powerplay",
    "Crew Lounge",
    "Universal Cartographics",
    "Outfitting",
    "Livery",
    "Shop",
    "Shipyard",
    "Construction Services",
    "Vista Genomics",
    "Bartender",
    "Pioneer Supplies",
    "Apex Interstellar",
    "Fleet Carrier Fuel",
    "Fleet Carrier Management",
    "Tuning",
    "Frontline Solutions",
    "Refinery Contact",
    "Redemption Office",
    "Technology Broker",
    "Squadron Bank",
    "Material Trader",
    "Fleet Carrier Administration",
    "On Dock Mission",
    "Fleet Carrier Vendor",
]


class SpanshTools:
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

    async def _fetch_stations_from_spansh(
        self, from_system: str, max_distance_ly: float, services: list[str]
    ) -> dict[str, Any]:
        """One POST to the Spansh station search (network, no retry, TIMEOUT
        seconds). Sends only the system name, the radius and the service names:
        stations nearest first, fleet carriers excluded, every service in
        services required (one filter entry per service). Asks for
        STATIONS_ASKED_FOR stations, more than the pilot gets, because the
        caller drops junk systems afterwards. The User-Agent is set here, the
        http client is closed after the call.
        Returns the JSON answer of Spansh as it is: "reference" (with the name
        of the searched system as Spansh spells it) and "results" (the
        stations, nearest first, an empty list when none is in range).
        Raises httpx errors (timeout, no network, error status) and ValueError
        for an unknown system (Spansh answers it with HTTP 400) and for an
        answer that is not JSON."""
        filters: dict[str, Any] = {
            "distance": {"min": "0", "max": str(max_distance_ly)},
            "type": {"value": [FLEET_CARRIER_TYPE], "logic": "NOT"},
        }
        if services:
            filters["services"] = [{"name": service} for service in services]
        body = {
            "filters": filters,
            "sort": [{"distance": {"direction": "asc"}}],
            "size": STATIONS_ASKED_FOR,
            "page": 0,
            "reference_system": from_system,
        }

        async with self.client_factory() as client:
            response = await client.post(
                STATION_SEARCH_URL,
                json=body,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )

        if response.status_code == 400:
            raise ValueError(f"System '{from_system}' not found")
        response.raise_for_status()

        try:
            return response.json()
        except ValueError as e:
            raise ValueError("Spansh returned an invalid response") from e

    async def _run_lookup_if_enabled_or_return_error(
        self, work: Callable[[], Awaitable[dict[str, Any]]]
    ) -> ToolReturn:
        """The part every tool shares. Returns an error ToolReturn without
        calling work (so without any request) when the external_apis switch is
        off. Otherwise awaits work and wraps its dict in a ToolReturn with
        metadata is_error=False.
        A ValueError from work (unknown system or service, unreadable answer;
        its text is passed on as it is) and any httpx.HTTPError (timeout, no
        network, error status) become an error ToolReturn with a sentence for
        the pilot. Other exceptions (for example a KeyError when Spansh changes
        its answer) are not caught here and end the LLM turn."""
        if not self.settings_service.get_settings().external_apis.enabled:
            return self._error_tool_return("Outside lookups are disabled by the user.")

        try:
            answer = await work()
        except httpx.TimeoutException:
            return self._error_tool_return("Spansh did not answer in time.")
        except httpx.HTTPStatusError as e:
            return self._error_tool_return(
                f"Spansh answered with an error code: {e.response.status_code}."
            )
        except httpx.HTTPError:
            return self._error_tool_return("Spansh did not answer.")
        except ValueError as e:
            return self._error_tool_return(str(e))

        return ToolReturn(return_value=answer, metadata={"is_error": False})

    def _name_or_current_system(self, system_name: str) -> str:
        """Gives system_name back, or the system the pilot is in now when
        system_name is an empty string. Reads the game state, changes nothing.
        Raises ValueError when system_name is empty and the current system is
        not known yet (the game state holds an empty value, because the game
        has not written one)."""
        if system_name:
            return system_name
        current_system = (
            self.game_state_protocol.get_game_stats().navigation.current_star_system
        )
        if not current_system:
            raise ValueError("The current system is not known yet.")
        return current_system

    @staticmethod
    def _spell_services_or_raise_if_unknown(services: list[str]) -> list[str]:
        """Gives every service back as Spansh spells it, in the same order, so
        "repair" works as "Repair" (the match ignores letter case, a typo is
        not corrected). An empty list gives an empty list.
        Raises ValueError naming every service Spansh does not have, each with
        up to 3 closest known names (all known names are listed when none is
        close), so the LLM can pick one. Nothing is sent to the network."""
        known_by_lowercase_name = {name.lower(): name for name in KNOWN_SERVICES}
        spelled = []
        problems = []
        for service in services:
            known_name = known_by_lowercase_name.get(service.lower())
            if known_name:
                spelled.append(known_name)
                continue
            close_names = difflib.get_close_matches(
                service, KNOWN_SERVICES, n=3, cutoff=0.4
            )
            problems.append(
                f"'{service}' (closest: {', '.join(close_names)})"
                if close_names
                else f"'{service}'"
            )
        if problems:
            raise ValueError(
                f"Unknown service: {'; '.join(problems)}. "
                f"Known services: {', '.join(KNOWN_SERVICES)}."
            )
        return spelled

    @tr.register_tool(
        name="find_stations",
        readable_name="Find Stations",
        param_name="from_system, max_distance_ly, services",
    )
    async def find_stations(
        self,
        from_system: str = "",
        max_distance_ly: float = 50,
        services: list[str] | None = None,
    ) -> ToolReturn:
        """Find the nearest stations in the galaxy around a star system, from
        outside data: use it for "where is the nearest Material Trader",
        "where can I repair and refuel" and similar. Leave from_system empty to
        search around the system the pilot is in now. max_distance_ly is the
        search radius in light years. services is a list of service names and
        a station must have all of them, for example ["Repair", "Refuel"],
        ["Material Trader"], ["Interstellar Factors Contact"], ["Technology
        Broker"] or ["Black Market"]. Leave it empty to list any stations.
        Answers with a dict of "from_system" (as Spansh spells it) and
        "stations": at most the 5 nearest stations (fleet carriers and the
        junk system "Test" left out), nearest first: name, system,
        distance_ly, distance_from_arrival_ls, type and, for a Material
        Trader, material_trader_kind (Raw, Encoded or Manufactured). An empty
        stations list means nothing was found within the radius, which is not
        an error. Answers with an error text when lookups are switched off,
        the current system is not known yet, the system or a service is
        unknown (the error lists the known services), or Spansh does not
        answer."""

        async def look_up_stations() -> dict[str, Any]:
            system_name = self._name_or_current_system(from_system)
            spelled_services = self._spell_services_or_raise_if_unknown(services or [])
            answer = await self._fetch_stations_from_spansh(
                system_name, max_distance_ly, spelled_services
            )
            stations = [
                self._pick_station_fields_for_pilot(station)
                for station in answer["results"]
                if station["system_name"].lower() not in JUNK_SYSTEM_NAMES
            ]
            return {
                "from_system": answer["reference"]["name"],
                "stations": stations[:MAX_STATIONS_SHOWN],
            }

        return await self._run_lookup_if_enabled_or_return_error(look_up_stations)

    @staticmethod
    def _pick_station_fields_for_pilot(station: dict[str, Any]) -> dict[str, Any]:
        """Keeps from a Spansh station only name, system (system_name), type,
        distance_ly (distance rounded to two decimals) and
        distance_from_arrival_ls (distance_to_arrival rounded to whole light
        seconds, 0 when Spansh does not know it). The services and everything
        else are dropped. material_trader_kind (from material_trader) is there
        only for a station that has a Material Trader, for the others the key
        is missing, not None.
        Raises KeyError when Spansh leaves out name, system_name, distance or
        type."""
        shortened = {
            "name": station["name"],
            "system": station["system_name"],
            "distance_ly": round(station["distance"], 2),
            "distance_from_arrival_ls": round(station.get("distance_to_arrival") or 0),
            "type": station["type"],
        }
        if station.get("material_trader"):
            shortened["material_trader_kind"] = station["material_trader"]
        return shortened

    @staticmethod
    def _error_tool_return(text: str) -> ToolReturn:
        """A ToolReturn whose value is text for the pilot and whose metadata
        says is_error=True, so COMMS shows an error and the LLM tells the pilot.
        Nothing is raised, so the LLM turn goes on."""
        return ToolReturn(return_value=text, metadata={"is_error": True})
