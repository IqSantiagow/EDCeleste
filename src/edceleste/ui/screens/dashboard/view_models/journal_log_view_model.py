from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from edceleste.services.models.game_events import (
    ApproachBodyEvent,
    ApproachSettlementEvent,
    CommanderEvent,
    DiedEvent,
    DockedEvent,
    DockingGrantedEvent,
    FSDJumpEvent,
    FSDTargetEvent,
    FuelScoopEvent,
    GameEvent,
    LeaveBodyEvent,
    LoadedGameEvent,
    LoadoutEvent,
    LocationEvent,
    PromotionEvent,
    RankEvent,
    RefuelAllEvent,
    ReputationEvent,
    ReservoirReplenishedEvent,
    ResurrectEvent,
    StartJumpEvent,
    SupercruiseDestinationDropEvent,
    SupercruiseEntryEvent,
    SupercruiseExitEvent,
    UndockedEvent,
    UnknownCheckedEvent,
)
from edceleste.services.models.rank_ladders import (
    COMBAT_RANKS,
    EXPLORATION_RANKS,
    TRADE_RANKS,
    rank_name,
)

# Entry category. It doubles as the filter value and as the row's CSS class,
# so it has to match ui/css.tcss (WidgetShipLogRow.log-nav and friends).
CATEGORY_NAV = "log-nav"
CATEGORY_COMBAT = "log-combat"
CATEGORY_TOOLS = "log-tools"
CATEGORY_OTHER = "log-other"


def format_thousands(value: int) -> str:
    """1284 -> '1 284'"""
    return f"{value:,}".replace(",", " ")


def read_system_name(event: GameEvent) -> str:
    """System name for the SYSTEM column.

    Only events that actually carry a system name fill it in. We do not
    remember the last known system - this view model is stateless.
    """
    if isinstance(event, FSDTargetEvent):
        return event.Name
    return getattr(event, "StarSystem", None) or ""


def _details_fsd_jump(event: FSDJumpEvent) -> str:
    return f"Arrived · {event.JumpDist:.2f} ly travelled"


def _details_start_jump(event: StartJumpEvent) -> str:
    if event.JumpType != "Hyperspace":
        return "Supercruise charging"
    if event.StarClass:
        return f"Hyperspace charging → {event.StarSystem} · class {event.StarClass}"
    return f"Hyperspace charging → {event.StarSystem}"


def _details_fsd_target(event: FSDTargetEvent) -> str:
    return f"Class {event.StarClass} · {event.RemainingJumpsInRoute} jumps left"


def _details_docked(event: DockedEvent) -> str:
    return f"{event.StationName} · {event.StationType}"


def _details_undocked(event: UndockedEvent) -> str:
    return event.StationName


def _details_docking_granted(event: DockingGrantedEvent) -> str:
    return f"{event.StationName} · pad {event.LandingPad}"


def _details_location(event: LocationEvent) -> str:
    if event.Docked and event.StationName:
        return f"Docked · {event.StationName}"
    if event.Body:
        return f"At {event.Body}"
    return "In open space"


def _details_supercruise_entry(event: SupercruiseEntryEvent) -> str:
    return "Left normal space"


def _details_supercruise_exit(event: SupercruiseExitEvent) -> str:
    return f"Dropped at {event.Body}"


def _details_supercruise_destination_drop(
    event: SupercruiseDestinationDropEvent,
) -> str:
    place = event.Type_Localised or event.Type
    if event.Threat:
        return f"{place} · threat {event.Threat}"
    return place


def _details_approach_body(event: ApproachBodyEvent) -> str:
    return f"Approaching {event.Body}"


def _details_leave_body(event: LeaveBodyEvent) -> str:
    return f"Leaving {event.Body}"


def _details_approach_settlement(event: ApproachSettlementEvent) -> str:
    return event.Name


def _details_fuel_scoop(event: FuelScoopEvent) -> str:
    return f"+{event.Scooped:.2f} T scooped · total {event.Total:.1f} T"


def _details_refuel_all(event: RefuelAllEvent) -> str:
    return f"Topped off · {format_thousands(event.Cost)} CR"


def _details_reservoir_replenished(event: ReservoirReplenishedEvent) -> str:
    return f"Main {event.FuelMain:.1f} T · reservoir {event.FuelReservoir:.2f} T"


def _details_loadout(event: LoadoutEvent) -> str:
    return (
        f"{event.ShipName} · hull {event.HullHealth:.0%} · "
        f"jump {event.MaxJumpRange:.2f} ly"
    )


def _details_loaded_game(event: LoadedGameEvent) -> str:
    return (
        f"{event.Commander} · {event.ShipName} · {format_thousands(event.Credits)} CR"
    )


def _details_commander(event: CommanderEvent) -> str:
    return f"CMDR {event.Name}"


def _details_rank(event: RankEvent) -> str:
    return (
        f"Combat {rank_name(COMBAT_RANKS, event.Combat)} · "
        f"Trade {rank_name(TRADE_RANKS, event.Trade)} · "
        f"Explore {rank_name(EXPLORATION_RANKS, event.Explore)}"
    )


# A promotion carries only the ranks that changed. We have names for the three
# main ladders - anything else falls back to a bare number.
_PROMOTION_RANK_FIELDS = (
    "Combat",
    "Trade",
    "Explore",
    "Soldier",
    "Exobiologist",
    "Empire",
    "Federation",
    "CQC",
)

_PROMOTION_LADDERS = {
    "Combat": COMBAT_RANKS,
    "Trade": TRADE_RANKS,
    "Explore": EXPLORATION_RANKS,
}


def _details_promotion(event: PromotionEvent) -> str:
    promoted_texts = []
    for field_name in _PROMOTION_RANK_FIELDS:
        new_rank = getattr(event, field_name)
        if new_rank is None:
            continue
        ladder = _PROMOTION_LADDERS.get(field_name)
        readable_rank = rank_name(ladder, new_rank) if ladder else f"rank {new_rank}"
        promoted_texts.append(f"{field_name} rank → {readable_rank}")
    return " · ".join(promoted_texts)


def _details_reputation(event: ReputationEvent) -> str:
    return (
        f"Emp {event.Empire:.1f}% · Fed {event.Federation:.1f}% · "
        f"Ind {event.Independent:.1f}% · Ali {event.Alliance:.1f}%"
    )


def _details_died(event: DiedEvent) -> str:
    if event.KillerName:
        return f"Destroyed by {event.KillerName}"
    return "Destroyed"


def _details_resurrect(event: ResurrectEvent) -> str:
    return f"{event.Option} · {format_thousands(event.Cost)} CR"


# To add a new event: write a _details_* function and one line here,
# plus one line in _CATEGORIES.
_DETAILS_BUILDERS: dict[type, Callable] = {
    FSDJumpEvent: _details_fsd_jump,
    StartJumpEvent: _details_start_jump,
    FSDTargetEvent: _details_fsd_target,
    DockedEvent: _details_docked,
    UndockedEvent: _details_undocked,
    DockingGrantedEvent: _details_docking_granted,
    LocationEvent: _details_location,
    SupercruiseEntryEvent: _details_supercruise_entry,
    SupercruiseExitEvent: _details_supercruise_exit,
    SupercruiseDestinationDropEvent: _details_supercruise_destination_drop,
    ApproachBodyEvent: _details_approach_body,
    LeaveBodyEvent: _details_leave_body,
    ApproachSettlementEvent: _details_approach_settlement,
    FuelScoopEvent: _details_fuel_scoop,
    RefuelAllEvent: _details_refuel_all,
    ReservoirReplenishedEvent: _details_reservoir_replenished,
    LoadoutEvent: _details_loadout,
    LoadedGameEvent: _details_loaded_game,
    CommanderEvent: _details_commander,
    RankEvent: _details_rank,
    PromotionEvent: _details_promotion,
    ReputationEvent: _details_reputation,
    DiedEvent: _details_died,
    ResurrectEvent: _details_resurrect,
}

_CATEGORIES: dict[type, str] = {
    # NAV - movement, navigation, docking
    FSDJumpEvent: CATEGORY_NAV,
    StartJumpEvent: CATEGORY_NAV,
    FSDTargetEvent: CATEGORY_NAV,
    DockedEvent: CATEGORY_NAV,
    UndockedEvent: CATEGORY_NAV,
    DockingGrantedEvent: CATEGORY_NAV,
    LocationEvent: CATEGORY_NAV,
    SupercruiseEntryEvent: CATEGORY_NAV,
    SupercruiseExitEvent: CATEGORY_NAV,
    SupercruiseDestinationDropEvent: CATEGORY_NAV,
    ApproachBodyEvent: CATEGORY_NAV,
    LeaveBodyEvent: CATEGORY_NAV,
    ApproachSettlementEvent: CATEGORY_NAV,
    # COMBAT - death and rebuy
    DiedEvent: CATEGORY_COMBAT,
    ResurrectEvent: CATEGORY_COMBAT,
    # TOOLS - fuel and outfitting
    FuelScoopEvent: CATEGORY_TOOLS,
    RefuelAllEvent: CATEGORY_TOOLS,
    ReservoirReplenishedEvent: CATEGORY_TOOLS,
    LoadoutEvent: CATEGORY_TOOLS,
    # OTHER - pilot account and session
    LoadedGameEvent: CATEGORY_OTHER,
    CommanderEvent: CATEGORY_OTHER,
    RankEvent: CATEGORY_OTHER,
    PromotionEvent: CATEGORY_OTHER,
    ReputationEvent: CATEGORY_OTHER,
    UnknownCheckedEvent: CATEGORY_OTHER,
}


@dataclass(slots=True)
class JournalLogViewModel:
    timestamp: datetime
    event: str
    system: str
    details: str
    category: str

    @classmethod
    def from_event(cls, event: GameEvent) -> "JournalLogViewModel":
        build_details = _DETAILS_BUILDERS.get(type(event))
        return cls(
            timestamp=event.timestamp,
            event=event.event,
            system=read_system_name(event),
            details=build_details(event) if build_details else "",
            category=_CATEGORIES.get(type(event), CATEGORY_OTHER),
        )
