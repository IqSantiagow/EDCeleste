from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlayerStats:
    name: str
    ship: str
    credits: int


@dataclass(frozen=True, slots=True)
class NavigationStats:
    current_star_system: str
    system_security_level: str
    system_allegiance: str
    system_government: str
    system_economy: str
    system_second_economy: str
    system_population: int
    current_body: str
    is_in_supercruise: bool
    route_next_star_system: str
    route_remaining_jumps: int


@dataclass(frozen=True, slots=True)
class FlightDriveStats:
    fuel_level: float
    fuel_capacity: float
    fuel_reservoir: float
    is_scooping_fuel: bool
    max_jump_range: float
    fsd_module_item: str


@dataclass(frozen=True, slots=True)
class ShipStats:
    is_landing_gear_down: bool
    are_hardpoints_deployed: bool
    are_lights_on: bool
    are_shields_up: bool
    pips_system: int
    pips_engine: int
    pips_weapons: int
    cargo_current: float
    cargo_capacity: int
    legal_status: str
    hull_health: float
    unladen_mass: float
    rebuy_cost: int
    are_all_modules_healthy: bool


@dataclass(frozen=True, slots=True)
class GameStatsSnapshot:
    player: PlayerStats
    navigation: NavigationStats
    flight_drive: FlightDriveStats
    ship: ShipStats
