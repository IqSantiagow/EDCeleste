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
        async for game_state in self.game_state_protocol.stream_game_stats():
            yield ShipStatsViewModel(
                hull_pe=game_state.ship.hull_health,
                shields_percent=SHIELDS_UP_PERCENT
                if game_state.ship.are_shields_up
                else SHIELDS_DOWN_PERCENT,
                pips=(
                    game_state.ship.pips_system / 2,
                    game_state.ship.pips_engine / 2,
                    game_state.ship.pips_weapons / 2,
                ),
                gear=game_state.ship.is_landing_gear_down,
                hardpoints=game_state.ship.are_hardpoints_deployed,
                lights=game_state.ship.are_lights_on,
                shields=game_state.ship.are_shields_up,
                mass=game_state.ship.unladen_mass,
                cargo=game_state.ship.cargo_current,
                cargo_capacity=game_state.ship.cargo_capacity,
                legal_status=game_state.ship.legal_status,
                rebuy=game_state.ship.rebuy_cost,
                modules_healthy=game_state.ship.are_all_modules_healthy,
                ship_name=game_state.player.ship,
            )
