from collections.abc import AsyncGenerator
from edceleste.use_cases.app.stream_app_header_stats_usecase import (
    StreamAppHeaderStatsUseCase,
)
from edceleste.ui.screens.app.view_models.app_header_view_model import (
    AppHeaderViewModel,
)


class AppHeaderRepository:
    def __init__(
        self, stream_app_header_stats_usecase: "StreamAppHeaderStatsUseCase"
    ) -> None:
        """The header's only way to the game state, so the widget does not know
        any use case."""
        self.stream_app_header_stats_usecase = stream_app_header_stats_usecase

    async def stream_app_header_stats(
        self,
    ) -> AsyncGenerator["AppHeaderViewModel", None]:
        """Never ends on its own. Passes on one view model (commander, ship,
        credits) every time the game stats change. AppHeader is the only
        reader."""
        async for view_model in self.stream_app_header_stats_usecase():
            yield view_model
