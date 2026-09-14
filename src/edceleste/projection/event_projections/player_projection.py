import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    LoadedGameEvent,
    CommanderEvent,
    RankEvent,
    PromotionEvent,
    ReputationEvent,
    DiedEvent,
    ResurrectEvent,
    StatusEvent,
    StatusFlags,
    StatusFlags2,
)

logger = logging.getLogger(__name__)


class PlayerProjection(Projection):
    PROJECTION_STRING = (
        "Commander name is {0}.Commander has {1} of credits.Commander ship is {2}."
    )

    RANK_PROJECTION = "Commander ranks are Combat: {0}, Trade: {1}, Exploration: {2}."

    REPUTATION_PROJECTION = (
        "Commander reputation is Empire: {0:.1f}%, Federation: {1:.1f}%, "
        "Alliance: {2:.1f}%."
    )

    DEAD_PROJECTION = "Commander has been destroyed and is awaiting rebuy."

    ON_FOOT_PROJECTION = "Commander is currently on foot."
    IN_TAXI_PROJECTION = "Commander is currently riding a taxi."
    IN_SRV_PROJECTION = "Commander is currently driving an SRV."
    IN_FIGHTER_PROJECTION = "Commander is currently piloting a fighter."

    UNKNOWN_RANK = "Unranked"

    COMBAT_RANKS = (
        "Harmless",
        "Mostly Harmless",
        "Novice",
        "Competent",
        "Expert",
        "Master",
        "Dangerous",
        "Deadly",
        "Elite",
    )

    TRADE_RANKS = (
        "Penniless",
        "Mostly Penniless",
        "Peddler",
        "Dealer",
        "Merchant",
        "Broker",
        "Entrepreneur",
        "Tycoon",
        "Elite",
    )

    EXPLORATION_RANKS = (
        "Aimless",
        "Mostly Aimless",
        "Scout",
        "Surveyor",
        "Trailblazer",
        "Pathfinder",
        "Ranger",
        "Pioneer",
        "Elite",
    )

    def __init__(self):
        self.player_name = None
        self.player_credits = 0
        self.player_ship = None
        self.combat_rank = None
        self.trade_rank = None
        self.exploration_rank = None
        self.empire_reputation = None
        self.federation_reputation = None
        self.alliance_reputation = None
        self.is_alive = True
        self.is_on_foot = False
        self.is_in_taxi = False
        self.is_in_srv = False
        self.is_in_fighter = False

    def process_event(self, event: BaseModel):
        if isinstance(event, LoadedGameEvent):
            logger.debug("Received player state event: %s", event)
            self.player_name = event.Commander
            self.player_credits = event.Credits
            self.player_ship = event.Ship_Localised or event.Ship
            self.is_alive = True
            return

        if isinstance(event, CommanderEvent):
            logger.debug("Received player state event: %s", event)
            self.player_name = event.Name
            return

        if isinstance(event, RankEvent):
            logger.debug("Received player state event: %s", event)
            self.combat_rank = event.Combat
            self.trade_rank = event.Trade
            self.exploration_rank = event.Explore
            return

        if isinstance(event, PromotionEvent):
            logger.debug("Received player state event: %s", event)
            if event.Combat is not None:
                self.combat_rank = event.Combat
            if event.Trade is not None:
                self.trade_rank = event.Trade
            if event.Explore is not None:
                self.exploration_rank = event.Explore
            return

        if isinstance(event, ReputationEvent):
            logger.debug("Received player state event: %s", event)
            self.empire_reputation = event.Empire
            self.federation_reputation = event.Federation
            self.alliance_reputation = event.Alliance
            return

        if isinstance(event, DiedEvent):
            logger.debug("Received player state event: %s", event)
            self.is_alive = False
            return

        if isinstance(event, ResurrectEvent):
            logger.debug("Received player state event: %s", event)
            self.is_alive = True
            return

        if isinstance(event, StatusEvent):
            logger.debug("Received player state event: %s", event)
            self.is_in_srv = bool(event.Flags & StatusFlags.InSRV)
            self.is_in_fighter = bool(event.Flags & StatusFlags.InFighter)
            self.is_on_foot = bool(event.Flags2 & StatusFlags2.OnFoot)
            self.is_in_taxi = bool(event.Flags2 & StatusFlags2.InTaxi)
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        if not self.player_name or not self.player_ship:
            logger.warning("Player state not set. Does the game started?")

        projection_string = self.PROJECTION_STRING.format(
            self.player_name, self.player_credits, self.player_ship
        )

        # Only emit the rank line once every rank is known; PromotionEvent can
        # set ranks independently, so a partially populated state would
        # otherwise leak literal "None" values into the LLM projection.
        if None not in (self.combat_rank, self.trade_rank, self.exploration_rank):
            projection_string += self.RANK_PROJECTION.format(
                self.__rank_name(self.COMBAT_RANKS, self.combat_rank),
                self.__rank_name(self.TRADE_RANKS, self.trade_rank),
                self.__rank_name(self.EXPLORATION_RANKS, self.exploration_rank),
            )

        if self.empire_reputation is not None:
            projection_string += self.REPUTATION_PROJECTION.format(
                self.empire_reputation,
                self.federation_reputation,
                self.alliance_reputation,
            )

        if not self.is_alive:
            projection_string += self.DEAD_PROJECTION

        if self.is_on_foot:
            projection_string += self.ON_FOOT_PROJECTION
        elif self.is_in_taxi:
            projection_string += self.IN_TAXI_PROJECTION
        elif self.is_in_srv:
            projection_string += self.IN_SRV_PROJECTION
        elif self.is_in_fighter:
            projection_string += self.IN_FIGHTER_PROJECTION

        return projection_string

    @staticmethod
    def __rank_name(ladder: tuple[str, ...], value) -> str:
        if value is not None and 0 <= value < len(ladder):
            return ladder[value]
        return PlayerProjection.UNKNOWN_RANK
