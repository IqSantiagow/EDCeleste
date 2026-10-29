import logging

from pydantic import BaseModel

from edceleste.projection.event_projections.projection import Projection
from edceleste.services.models.game_events import (
    FSDJumpEvent,
    LocationEvent,
    NavRouteEvent,
)

logger = logging.getLogger(__name__)

# How many systems after the current one are named for the LLM. A list of forty
# system names tells it nothing more.
NEXT_SYSTEMS_COUNT = 3


class RouteProjection(Projection):
    ROUTE_PROJECTION = "Plotted route: destination {0}, {1} left."

    NEXT_SYSTEMS_PROJECTION = "Next systems on the route: {0}."

    NO_ROUTE_PROJECTION = "No route is plotted."

    def __init__(self):
        """current_star_system stays None until a Location or FSDJump event
        names it. route_system_names stays empty and has_read_route_file stays
        False until NavRoute.json is read: before that the route is not known,
        which is not the same as "no route"."""
        self.current_star_system = None
        self.route_system_names: list[str] = []
        self.has_read_route_file = False

    def process_event(self, event: BaseModel) -> None:
        """- Location and FSDJump -> remember the system the ship is in. The
          journal is read before NavRoute.json, so at the start the system is
          already known when the route arrives.
        - NavRouteEvent (NavRoute.json) -> the whole route replaces the old
          one, and the route counts as known from now on. A cleared route is
          the same class (its event name is NavRouteClear) with an empty route,
          so it clears the old one.
        Any other event is skipped. Returns nothing, raises nothing."""
        if isinstance(event, (LocationEvent, FSDJumpEvent)):
            logger.debug("Received route event: %s", event)
            self.current_star_system = event.StarSystem
            return

        if isinstance(event, NavRouteEvent):
            logger.debug("Received route event: %s", event)
            self.has_read_route_file = True
            self.route_system_names = [system.StarSystem for system in event.Route]
            return

        logger.debug("Received event but not withing allowed events. Skipping...")

    def create_projection(self) -> str:
        """Empty string until NavRoute.json has been read. After that:
        - an empty route, or the ship is already in the last system of it ->
          "No route is plotted." (arriving at the destination ends the route,
          the game clears it then too),
        - otherwise two sentences: the destination (the last system) with the
          jumps left, like "5 jumps left" or "1 jump left", and the first
          NEXT_SYSTEMS_COUNT systems after the current one.
        The jumps left are the systems after the place of the current system
        in the route, so every jump takes one jump off. When the current
        system is unknown or not on the route, the first system of the route is
        counted as the place the ship is in. Reads the fields only, raises
        nothing."""
        if not self.has_read_route_file:
            return ""

        position = self.__index_of_current_system_on_route_or_zero()
        systems_ahead = self.route_system_names[position + 1 :]
        if not systems_ahead:
            return self.NO_ROUTE_PROJECTION

        jump_word = "jump" if len(systems_ahead) == 1 else "jumps"
        return " ".join(
            [
                self.ROUTE_PROJECTION.format(
                    systems_ahead[-1], f"{len(systems_ahead)} {jump_word}"
                ),
                self.NEXT_SYSTEMS_PROJECTION.format(
                    ", ".join(systems_ahead[:NEXT_SYSTEMS_COUNT])
                ),
            ]
        )

    def __index_of_current_system_on_route_or_zero(self) -> int:
        """Index of the current system in the route, counted from 0. Returns 0
        when the current system is unknown or is not on the route, so 0 also
        means "not on the route". With an empty route it returns 0 as well,
        and the caller gets no systems ahead. Reads the fields only."""
        if self.current_star_system in self.route_system_names:
            return self.route_system_names.index(self.current_star_system)
        return 0
