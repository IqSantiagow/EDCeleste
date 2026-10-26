from collections.abc import AsyncGenerator
from edceleste.use_cases.app.stream_app_header_stats_usecase import (
    StreamAppHeaderStatsUseCase,
)
from edceleste.use_cases.app.stream_service_statuses_usecase import (
    StreamServiceStatusesUseCase,
)
from edceleste.ui.screens.app.view_models.app_header_view_model import (
    AppHeaderViewModel,
)
from edceleste.ui.screens.app.view_models.service_statuses_view_model import (
    ServiceStatusesViewModel,
)


class AppHeaderRepository:
    def __init__(
        self,
        stream_app_header_stats_usecase: "StreamAppHeaderStatsUseCase",
        stream_service_statuses_usecase: "StreamServiceStatusesUseCase",
    ) -> None:
        """The header's only way to the game state and to the state of the
        services, so the widget does not know any use case."""
        self.stream_app_header_stats_usecase = stream_app_header_stats_usecase
        self.stream_service_statuses_usecase = stream_service_statuses_usecase

    async def stream_app_header_stats(
        self,
    ) -> AsyncGenerator["AppHeaderViewModel", None]:
        """Never ends on its own. Passes on one view model (commander, ship,
        credits) every time the game stats change. AppHeader is the only
        reader."""
        async for view_model in self.stream_app_header_stats_usecase():
            yield view_model

    async def stream_service_statuses(
        self,
    ) -> AsyncGenerator["ServiceStatusesViewModel", None]:
        """Never ends on its own. Passes on one view model with the status of
        LLM, TTS, MIC and JRNL every time one of them changes. Every AppHeader
        that is on the screen starts its own stream."""
        async for view_model in self.stream_service_statuses_usecase():
            yield view_model
