import difflib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field
from pydantic_ai import ToolReturn
from edceleste.adapters.tools.tool_register import ToolRegister as tr
from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.services.settings_service import SettingsService

STATION_SEARCH_URL = "https://spansh.co.uk/api/stations/search"
SYSTEM_SEARCH_URL = "https://spansh.co.uk/api/systems/search"
USER_AGENT = "EDCeleste"
TIMEOUT = 10
MAX_STATIONS_SHOWN = 5
# More than MAX_STATIONS_SHOWN, because junk entries are dropped after the search.
STATIONS_ASKED_FOR = 20
# A short list keeps a long answer out of the conversation history.
MAX_SYSTEMS_SHOWN = 10
# More than MAX_SYSTEMS_SHOWN, because junk entries are dropped after the search.
SYSTEMS_ASKED_FOR = 20
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

# Spansh module names, from GET /api/stations/field_values/modules on 2026-11-26.
KNOWN_MODULES = [
    "Fuel Scoop",
    "Sensors",
    "Power Distributor",
    "Life Support",
    "Shield Cell Bank",
    "Auto Field-Maintenance Unit",
    "Power Plant",
    "Shield Generator",
    "Thrusters",
    "Frame Shift Drive",
    "Frame Shift Drive (SCO)",
    "Lightweight Alloy",
    "Reinforced Alloy",
    "Military Grade Composite",
    "Refinery",
    "Prospector Limpet Controller",
    "Frame Shift Drive Interdictor",
    "Hatch Breaker Limpet Controller",
    "Fuel Transfer Limpet Controller",
    "Reactive Surface Composite",
    "Mirrored Surface Composite",
    "Collector Limpet Controller",
    "Repair Limpet Controller",
    "Hull Reinforcement Package",
    "Beam Laser",
    "Pulse Laser",
    "Cannon",
    "Module Reinforcement Package",
    "Multi-Cannon",
    "Fuel Tank",
    "Planetary Vehicle Hangar",
    "Burst Laser",
    "Cargo Rack",
    "Bi-Weave Shield Generator",
    "Fragment Cannon",
    "Shield Booster",
    "Sub-Surface Displacement Missile",
    "Recon Limpet Controller",
    "Cargo Scanner",
    "Economy Class Passenger Cabin",
    "Kill Warrant Scanner",
    "Support Focused Power Distributor",
    "Frame Shift Wake Scanner",
    "Pulse Wave Analyser",
    "Missile Rack",
    "Torpedo Pylon",
    "Mining Laser",
    "Vessel Hangar",
    "Business Class Passenger Cabin",
    "Large Planetary Vehicle Hangar",
    "Mk II Large Planetary Vehicle Hangar",
    "MkII Economy Class Passenger Cabin",
    "Prismatic Shield Generator",
    "Mk II Cargo Rack",
    "Seeker Missile Rack",
    "Mine Launcher",
    "Xeno Multi Limpet Controller",
    "Seismic Charge Launcher",
    "Mk II Vessel Hangar",
    "Plasma Accelerator",
    "First Class Passenger Cabin",
    "MkII Business Class Passenger Cabin",
    "Mining Multi Limpet Controller",
    "Operations Multi Limpet Controller",
    "Rescue Multi Limpet Controller",
    "Extended Cargo Rack",
    "Rail Gun",
    "Decontamination Limpet Controller",
    "Chaff Launcher",
    "Heat Sink Launcher",
    "Double Screaming Fragment Cannon",
    "Standard Docking Computer",
    "Supercruise Assist",
    "Research Limpet Controller",
    "Electronic Countermeasure",
    "Advanced Docking Computer",
    "Shock Mine Launcher",
    "Abrasion Blaster",
    "Advanced Planetary Approach Suite",
    "AX Multi-Cannon",
    "Mk II Mining Multi-Limpet Controller",
    "AX Missile Rack",
    "Long Range Detailed Surface Scanner",
    "Meta Alloy Hull Reinforcement",
    "Fighter Hangar",
    "Planetary Approach Suite",
    "Far-Reaching Abrasion Blaster",
    "Lockdown Seeker Missile Rack",
    "Long Range Mining Laser",
    "Luxury Class Passenger Cabin",
    "Enduring Feedback Rail Gun",
    "Rapid Phase Multi-Cannon",
    "Point Defence",
    "Mk II Plasma Shock Accelerator",
    "Heavy Duty Module Reinforcement Package",
    "Mining Volley Repeater",
    "Exposing Missiles",
    "Force Impact Cannon",
    "Regenerative Burst Laser",
    "Overloaded Beam Laser",
    "Mk II Agile Boost Thrusters",
    "Mk II Supercharge Optimised Frame Shift Drive (SCO)",
    "Enhanced AX Multi-Cannon",
    "Balanced Power Distributor",
    "Mk II Gravity Optimised Thrusters",
    "Remote Release Flak Launcher",
    "Detailed Surface Scanner",
    "Universal Multi Limpet Controller",
    "Mk II Ablative Lightweight Alloys",
    "Mk II Ablative Reinforced Alloys",
    "Mk II Ablative Military Grade Composite",
    "Mk II Ablative Reactive Surface Composite",
    "Mk II Ablative Mirrored Surface Composite",
    "Xeno Scanner",
    "Mk II Economy Class Passenger Cabin",
    "Pack-Hound Missile Rack",
    "Imperial Hammer Rail Gun",
    "Enforcer Cannon",
    "Shutdown Field Neutraliser",
    "Advanced Plasma Accelerator",
    "Retributor Beam Laser",
    "Pulse Disruptor Laser",
    "Concord Cannon",
    "Rocket Propelled FSD Disruptor",
    "Mining Lance",
    "Pacifier Frag-Cannon",
    "Cytoscrambler Burst Laser",
    "Thargoid Pulse Neutraliser",
    "Enhanced Xeno Scanner",
    "Mk II Business Class Passenger Cabin",
    "Shock Cannon",
    "Advanced Multi-Cannon",
    "Advanced Missile Rack",
    "Enhanced AX Missile Rack",
    "High-Yield Enzyme Missile Rack",
    "Corrosion Resistant Cargo Rack",
    "Enzyme Missile Rack",
    "Remote Release Flechette Launcher",
    "Guardian Shield Reinforcement",
    "Experimental Weapon Stabiliser",
    "Guardian Hull Reinforcement",
    "Guardian Module Reinforcement",
    "Guardian Hybrid Power Distributor",
    "Guardian Hybrid Power Plant",
    "Guardian Shard Cannon",
    "Guardian Plasma Charger",
    "Caustic Sink Launcher",
    "Guardian FSD Booster",
    "Pulse Wave Xeno Scanner",
    "Sub-Surface Extraction Missile",
    "Guardian Nanite Torpedo Pylon",
    "Guardian Gauss Cannon",
    "Enhanced Performance Thrusters",
]

# Spansh ship names, from GET /api/stations/field_values/ships on 2026-11-26.
KNOWN_SHIPS = [
    "Sidewinder",
    "Hauler",
    "Cobra MkIII",
    "Type-6 Transporter",
    "Adder",
    "Eagle",
    "Krait MkII",
    "Panther Clipper MkII",
    "Cobra MkV",
    "Viper MkIII",
    "Krait Phantom",
    "Asp Explorer",
    "Type-8 Transporter",
    "Type-7 Transporter",
    "Mandalay",
    "Dolphin",
    "Viper MkIV",
    "Type-9 Heavy",
    "Diamondback Explorer",
    "Python",
    "Caspian Explorer",
    "Vulture",
    "Type-11 Prospector",
    "Keelback",
    "Anaconda",
    "Asp Scout",
    "Diamondback Scout",
    "Python MkII",
    "Lynx Highliner",
    "Beluga Liner",
    "Kestrel Mk II",
    "Mamba",
    "Orca",
    "Corsair",
    "Fer-de-Lance",
    "Cobra MkIV",
    "Type-10 Defender",
    "Alliance Chieftain",
    "Alliance Challenger",
    "Imperial Courier",
    "Imperial Eagle",
    "Alliance Crusader",
    "Imperial Clipper",
    "Federal Corvette",
    "Imperial Cutter",
    "Federal Dropship",
    "Federal Assault Ship",
    "Federal Gunship",
    "Anaconda Mk II",
]


class ModuleQuery(BaseModel):
    """One module the pilot wants to buy. The LLM sends the class as "class"
    (a Python keyword, so the field is module_class here). An empty class or
    rating means any class or any rating."""

    name: str = Field(
        description='Module name as the game spells it, e.g. "Frame Shift Drive"'
    )
    module_class: int | None = Field(
        default=None, alias="class", description="Module size class, 0 to 8"
    )
    rating: str | None = Field(
        default=None, description="Module rating letter, A (best) to I"
    )


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

    async def _fetch_raw_station_search_answer(
        self,
        from_system: str,
        max_distance_ly: float,
        services: list[str],
        modules: list[ModuleQuery],
        ships: list[str],
    ) -> dict[str, Any]:
        """One search at the Spansh station search (see
        _post_search_to_spansh for the network part and the errors). Sends only
        the system name, the radius and the names of services, modules and
        ships: stations nearest first, fleet carriers excluded, every service,
        module and ship required (one filter entry each). A module entry has a
        class or a rating only when the ModuleQuery has one. Asks for
        STATIONS_ASKED_FOR stations, more than the pilot gets, because the
        caller drops junk systems afterwards.
        Returns the JSON answer of Spansh as it is: "reference" (with the name
        of the searched system as Spansh spells it) and "results" (the
        stations, nearest first, an empty list when none is in range)."""
        filters: dict[str, Any] = {
            "distance": {"min": "0", "max": str(max_distance_ly)},
            "type": {"value": [FLEET_CARRIER_TYPE], "logic": "NOT"},
        }
        if services:
            filters["services"] = [{"name": service} for service in services]
        if modules:
            filters["modules"] = []
            for module in modules:
                module_filter: dict[str, Any] = {"name": {"value": [module.name]}}
                if module.module_class is not None:
                    module_filter["class"] = {"value": [str(module.module_class)]}
                if module.rating:
                    module_filter["rating"] = {"value": [module.rating]}
                filters["modules"].append(module_filter)
        if ships:
            filters["ships"] = [{"name": {"value": [ship]}} for ship in ships]
        body = {
            "filters": filters,
            "sort": [{"distance": {"direction": "asc"}}],
            "size": STATIONS_ASKED_FOR,
            "page": 0,
            "reference_system": from_system,
        }
        return await self._post_search_to_spansh(STATION_SEARCH_URL, body)

    async def _fetch_raw_system_search_answer(
        self, from_system: str, max_distance_ly: float, controlling_faction: str
    ) -> dict[str, Any]:
        """One search at the Spansh system search (see _post_search_to_spansh
        for the network part and the errors). Sends only the system name, the
        radius and the faction name: systems nearest first, and when
        controlling_faction is not empty only the systems that faction
        controls (Spansh matches the name exactly, letter case too). An empty
        controlling_faction is no filter. Asks for SYSTEMS_ASKED_FOR systems,
        more than the pilot gets, because the caller drops junk systems
        afterwards.
        Returns the JSON answer of Spansh as it is: "count" (all matching
        systems, also those past this page), "reference" (with the name of the
        searched system as Spansh spells it) and "results" (the systems,
        nearest first, the searched system itself included, an empty list
        when none matches)."""
        filters: dict[str, Any] = {
            "distance": {"min": "0", "max": str(max_distance_ly)},
        }
        if controlling_faction:
            filters["controlling_minor_faction"] = {"value": [controlling_faction]}
        body = {
            "filters": filters,
            "sort": [{"distance": {"direction": "asc"}}],
            "size": SYSTEMS_ASKED_FOR,
            "page": 0,
            "reference_system": from_system,
        }
        return await self._post_search_to_spansh(SYSTEM_SEARCH_URL, body)

    async def _post_search_to_spansh(
        self, url: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        """One POST of body as JSON to a Spansh search url (network, no retry,
        TIMEOUT seconds). The User-Agent is set here. A new http client is
        made for the call and closed after it, also when it fails.
        Returns the JSON answer as it is, its shape is not checked.
        Raises:
        - ValueError "System '<body["reference_system"]>' not found" for every
          HTTP 400 (that is how Spansh answers an unknown system),
        - httpx.HTTPStatusError for any other 4xx or 5xx status,
        - httpx.TimeoutException when Spansh does not answer in time, other
          httpx.HTTPError (for example ConnectError) when there is no network,
        - ValueError "Spansh returned an invalid response" for an answer that
          is not JSON."""
        async with self.client_factory() as client:
            response = await client.post(
                url,
                json=body,
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )

        if response.status_code == 400:
            raise ValueError(f"System '{body['reference_system']}' not found")
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
    def _spell_names_or_raise_if_unknown(
        names: list[str], known_names: list[str], kind: str
    ) -> list[str]:
        """Gives every name back as Spansh spells it (one of known_names), in
        the same order, so "repair" works as "Repair" (the match ignores letter
        case, a typo is not corrected). An empty list gives an empty list.
        kind ("service", "module" or "ship") only goes into the error text.
        Raises ValueError naming every name Spansh does not have, each with up
        to 3 closest known names, followed by all known names, so the LLM can
        pick one. Nothing is sent to the network."""
        known_by_lowercase_name = {name.lower(): name for name in known_names}
        spelled = []
        problems = []
        for name in names:
            known_name = known_by_lowercase_name.get(name.lower())
            if known_name:
                spelled.append(known_name)
                continue
            close_names = difflib.get_close_matches(name, known_names, n=3, cutoff=0.4)
            problems.append(
                f"'{name}' (closest: {', '.join(close_names)})"
                if close_names
                else f"'{name}'"
            )
        if problems:
            raise ValueError(
                f"Unknown {kind}: {'; '.join(problems)}. "
                f"Known {kind}s: {', '.join(known_names)}."
            )
        return spelled

    @classmethod
    def _spell_modules_or_raise_if_unknown(
        cls, modules: list[ModuleQuery]
    ) -> list[ModuleQuery]:
        """Gives new ModuleQuery copies, in the same order, with the name as
        Spansh spells it and the rating in capitals ("a" becomes "A"). The
        class and the rating are not checked against a list: a wrong one
        (class 12, rating "Z") goes on and simply finds no station. An empty
        list gives an empty list; the given objects are not changed.
        Raises ValueError for unknown module names, with the closest known
        names, like _spell_names_or_raise_if_unknown with kind "module".
        Nothing is sent to the network."""
        spelled_names = cls._spell_names_or_raise_if_unknown(
            [module.name for module in modules], KNOWN_MODULES, "module"
        )
        return [
            module.model_copy(
                update={
                    "name": spelled_name,
                    "rating": module.rating.upper() if module.rating else None,
                }
            )
            for spelled_name, module in zip(spelled_names, modules, strict=True)
        ]

    @staticmethod
    def _station_sells_all_modules_and_ships(
        station: dict[str, Any], modules: list[ModuleQuery], ships: list[str]
    ) -> bool:
        """Checks the station's own "modules" list (entries with "name",
        "class" as a number and "rating" as a letter) and "ships" list
        (entries with "name") from Spansh, instead of trusting the search
        filter alone. A missing list counts as empty. Names are compared
        exactly, so they must already be spelled like Spansh. Services are
        not checked again here, the search filter is trusted for them.
        Returns True when every asked module (same name, and same class and
        rating when those were asked) and every asked ship is on the lists,
        also when nothing is asked; False when one is missing. This says what
        Spansh last saw at the station, which can be old.
        Raises KeyError when a Spansh entry lacks "name", "class" or
        "rating"."""
        sold_modules = station.get("modules") or []
        sold_ship_names = {ship["name"] for ship in station.get("ships") or []}
        for module in modules:
            if not any(
                sold["name"] == module.name
                and (
                    module.module_class is None or sold["class"] == module.module_class
                )
                and (not module.rating or sold["rating"] == module.rating)
                for sold in sold_modules
            ):
                return False
        return all(ship in sold_ship_names for ship in ships)

    @staticmethod
    def _days_since_spansh_update(spansh_time: str | None) -> int | None:
        """Tells how old a piece of Spansh data is: the time from spansh_time
        (UTC, written like "2026-11-26T11:13:33Z") to now, as whole days
        rounded down, so 23 hours gives 0. A time in the future gives a
        negative number. Returns None when Spansh gave no time (None or an
        empty string). Reads the clock, changes nothing.
        Raises ValueError when the time is written in a form Python cannot
        read."""
        if not spansh_time:
            return None
        return (datetime.now(UTC) - datetime.fromisoformat(spansh_time)).days

    @tr.register_tool(
        name="find_stations",
        readable_name="Find Stations",
        param_name="from_system, max_distance_ly, services, modules, ships",
    )
    async def find_stations(
        self,
        from_system: str = "",
        max_distance_ly: float = 50,
        services: list[str] | None = None,
        modules: list[ModuleQuery] | None = None,
        ships: list[str] | None = None,
    ) -> ToolReturn:
        """Find the nearest stations in the galaxy around a star system, from
        outside data: use it for "where is the nearest Material Trader",
        "where can I repair and refuel", "where can I buy a 5A frame shift
        drive", "which station sells an Anaconda" and similar. Leave
        from_system empty to search around the system the pilot is in now.
        max_distance_ly is the search radius in light years. A station must
        have everything asked in services, modules and ships together; leave
        all three empty to list any stations.
        services is a list of service names, for example ["Repair",
        "Refuel"], ["Material Trader"], ["Interstellar Factors Contact"],
        ["Technology Broker"] or ["Black Market"].
        modules is a list of modules to buy, each with name (as the game
        spells it, for example "Frame Shift Drive", "Thrusters", "Fuel
        Scoop"), and optional class (a number) and rating (a letter): "a 5A
        frame shift drive and a 4D thruster" is [{"name": "Frame Shift
        Drive", "class": 5, "rating": "A"}, {"name": "Thrusters", "class": 4,
        "rating": "D"}].
        ships is a list of ship names to buy, for example ["Anaconda"].
        Answers with a dict of "from_system" (as Spansh spells it) and
        "stations": at most the 5 nearest stations (fleet carriers and the
        junk system "Test" left out), nearest first: name, system,
        distance_ly, distance_from_arrival_ls, type, for a Material Trader
        material_trader_kind (Raw, Encoded or Manufactured), when modules
        were asked outfitting_data_age_days and when ships were asked
        shipyard_data_age_days (how many days ago the outfitting or the
        shipyard of the station was last seen, null when unknown; old data
        is shown, tell the pilot its age). The list can be shorter than 5
        even when more stations are in range, because only the 20 nearest
        matches are fetched before the checks. An empty stations list means nothing
        was found within the radius, which is not an error. Answers with an error text
        when lookups are switched off, the current system is not known yet,
        the system, a service, a module or a ship is unknown (the error gives
        the closest known names), or Spansh does not answer."""

        async def look_up_stations() -> dict[str, Any]:
            system_name = self._name_or_current_system(from_system)
            spelled_services = self._spell_names_or_raise_if_unknown(
                services or [], KNOWN_SERVICES, "service"
            )
            spelled_modules = self._spell_modules_or_raise_if_unknown(modules or [])
            spelled_ships = self._spell_names_or_raise_if_unknown(
                ships or [], KNOWN_SHIPS, "ship"
            )
            answer = await self._fetch_raw_station_search_answer(
                system_name,
                max_distance_ly,
                spelled_services,
                spelled_modules,
                spelled_ships,
            )
            stations = []
            for station in answer["results"]:
                if station["system_name"].lower() in JUNK_SYSTEM_NAMES:
                    continue
                if not self._station_sells_all_modules_and_ships(
                    station, spelled_modules, spelled_ships
                ):
                    continue
                shortened = self._pick_station_fields_for_pilot(station)
                if spelled_modules:
                    shortened["outfitting_data_age_days"] = (
                        self._days_since_spansh_update(
                            station.get("outfitting_updated_at")
                        )
                    )
                if spelled_ships:
                    shortened["shipyard_data_age_days"] = (
                        self._days_since_spansh_update(
                            station.get("shipyard_updated_at")
                        )
                    )
                stations.append(shortened)
            return {
                "from_system": answer["reference"]["name"],
                "stations": stations[:MAX_STATIONS_SHOWN],
            }

        return await self._run_lookup_if_enabled_or_return_error(look_up_stations)

    @tr.register_tool(
        name="find_systems",
        readable_name="Find Systems",
        param_name="from_system, max_distance_ly, faction",
    )
    async def find_systems(
        self,
        from_system: str = "",
        max_distance_ly: float = 50,
        faction: str = "",
    ) -> ToolReturn:
        """Find the star systems around a star system, from outside data: use
        it for "which systems are within 20 light years of here" or "where is
        the nearest system of the faction X". Leave from_system empty to search
        around the system the pilot is in now. max_distance_ly is the search
        radius in light years; for a faction use a large one, for example 1000,
        because its systems can be far away. faction is the exact name of a
        minor faction, letter case included (for example "Mother Gaia"); with
        it only the systems that faction controls are listed, leave it empty to
        list all systems.
        Answers with a dict of "from_system" (as Spansh spells it), "systems":
        at most the 10 nearest systems (the junk system "Test" left out),
        nearest first, each with name and distance_ly (the searched system
        itself is there too, at 0 ly, but with a faction only when that faction
        controls it), and "systems_left_out": how many more systems match but
        are not listed (all matches Spansh counted, minus the ones it sent,
        plus the ones sent but cut by the limit of 10; a dropped "Test" is not
        counted, so it is never below 0). An empty systems list is not an
        error: nothing is within the radius, or no faction has exactly that
        name. Answers with an error text when lookups are switched off, the
        current system is not known yet, the system is unknown, or Spansh does
        not answer."""

        async def look_up_systems() -> dict[str, Any]:
            system_name = self._name_or_current_system(from_system)
            answer = await self._fetch_raw_system_search_answer(
                system_name, max_distance_ly, faction
            )
            systems_without_junk = [
                {"name": system["name"], "distance_ly": round(system["distance"], 2)}
                for system in answer["results"]
                if system["name"].lower() not in JUNK_SYSTEM_NAMES
            ]
            systems_shown = systems_without_junk[:MAX_SYSTEMS_SHOWN]
            systems_past_this_page = answer["count"] - len(answer["results"])
            systems_cut_from_this_page = len(systems_without_junk) - len(systems_shown)
            return {
                "from_system": answer["reference"]["name"],
                "systems": systems_shown,
                "systems_left_out": systems_past_this_page + systems_cut_from_this_page,
            }

        return await self._run_lookup_if_enabled_or_return_error(look_up_systems)

    @staticmethod
    def _pick_station_fields_for_pilot(station: dict[str, Any]) -> dict[str, Any]:
        """Keeps from a Spansh station only name, system (system_name), type,
        distance_ly (distance rounded to two decimals) and
        distance_from_arrival_ls (distance_to_arrival rounded to whole light
        seconds, 0 when Spansh does not know it). The services and everything
        else are dropped (find_stations adds the data age keys itself).
        material_trader_kind is the station's material_trader field (Raw,
        Encoded or Manufactured) and is there only when that field is not
        empty; for other stations the key is missing, not None.
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
