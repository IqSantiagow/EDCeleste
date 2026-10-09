from typing import AsyncGenerator

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.ui.screens.dashboard.view_models.game_stats_view_model import (
    ShipStatsViewModel,
)

SHIELDS_UP_PERCENT = 100.0
SHIELDS_DOWN_PERCENT = 0.0


class StreamShipStatsUseCase:
    def __init__(self, game_state_protocol: GameStateProtocol):
        self.game_state_protocol = game_state_protocol

    async def __call__(self) -> AsyncGenerator[ShipStatsViewModel, None]:
        """Never ends. Listens to the game stats stream and keeps only the ship
        card values. The current values come at once, then again after every
        Status.json update.

        - Shields are only up or down in the game data, so the bar shows 100 %
          or 0 %.
        - The game counts pips in halves (0-8), the card shows whole pips
          (0-4), so every pip value is divided by 2.
        """
        async for game_stats in self.game_state_protocol.stream_game_stats():
            yield ShipStatsViewModel(
                hull_health_fraction=game_stats.ship.hull_health,
                shields_percent=SHIELDS_UP_PERCENT
                if game_stats.ship.are_shields_up
                else SHIELDS_DOWN_PERCENT,
                pips=(
                    game_stats.ship.pips_system / 2,
                    game_stats.ship.pips_engine / 2,
                    game_stats.ship.pips_weapons / 2,
                ),
                gear=game_stats.ship.is_landing_gear_down,
                hardpoints=game_stats.ship.are_hardpoints_deployed,
                lights=game_stats.ship.are_lights_on,
                shields=game_stats.ship.are_shields_up,
                mass=game_stats.ship.unladen_mass,
                cargo=game_stats.ship.cargo_current,
                cargo_capacity=game_stats.ship.cargo_capacity,
                legal_status=game_stats.ship.legal_status,
                rebuy=game_stats.ship.rebuy_cost,
                modules_healthy=game_stats.ship.are_all_modules_healthy,
                ship_name=game_stats.player.ship,
            )
