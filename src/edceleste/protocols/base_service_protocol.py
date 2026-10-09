from typing import AsyncGenerator, Protocol

from edceleste.services.models.cold_start_status import ColdStartStatus


class BaseServiceProtocol(Protocol):
    def cold_start(self) -> "AsyncGenerator[ColdStartStatus, None]":
        """Startup check of one service, shown as one row in the system check
        screen. SystemCheckUseCase runs it once at app start, one service after
        another. This is where a service reads its settings for the first time,
        usually through its own reload_service().

        Every implementation keeps this order:
        1. First yield: a status with completed=False, so the row shows a
           spinner.
        2. Optional middle yields: still completed=False, only to show
           progress_text, e.g. a download.
        3. Last yield: completed=True. message=None means fine. A message means
           failed, or only a warning when is_warning=True. is_disabled=True
           means the pilot switched the service off.
        Errors go into the message, they are not raised. A failed status with
        is_critical=True stops the whole system check.
        """
        ...
