from dataclasses import dataclass


@dataclass
class FlightAndDriveViewModel:
    fuel: float
    fuel_capacity: float
    is_scooping: bool
    fuel_reservoir: float
    jump_range: float
    fsd_module: str


@dataclass
class NavigationStatsViewModel:
    system: str
    security: str
    body: str
    status: str
    allegiance: str
    government: str
    economy: str
    second_economy: str
    population: int
    route_next_system: str
    route_remaining_jumps: int


@dataclass
class ShipStatsViewModel:
    hull_pe: float
    shields_percent: float
    pips: tuple
    gear: bool
    hardpoints: bool
    lights: bool
    shields: bool
    mass: float
    cargo: float
    cargo_capacity: float
    legal_status: str
    rebuy: float
    modules_healthy: bool
    ship_name: str
