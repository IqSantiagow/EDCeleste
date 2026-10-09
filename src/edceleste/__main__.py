import logging

from textual.logging import TextualHandler

from edceleste.config.config import AppConfig
from edceleste.containers.main_container import MODULES_USING_PROVIDE, Container
from edceleste.ui.ui_app import UIApp


def main() -> None:
    """Entry point of the `edceleste` console script.

    1. Builds the DI container and loads .env into container.config. A
       missing or wrong LOGGING__LEVEL raises here, before anything starts.
    2. Wires MODULES_USING_PROVIDE, so their @inject defaults get real objects.
    3. Sends all logging to the Textual log at the level from .env.
    4. Runs the Textual app until the pilot closes it.
    An exception from the app is logged (without the traceback) and
    swallowed, so the process still exits normally.
    """
    container = Container()
    container.config.from_pydantic(AppConfig())  # type: ignore[call-arg]
    container.wire(modules=MODULES_USING_PROVIDE)

    log_level = container.config.logging.level()

    logging.basicConfig(level=getattr(logging, log_level), handlers=[TextualHandler()])

    logger = logging.getLogger(__name__)

    try:
        UIApp().run()
    except Exception as e:
        logger.error("Raised an exception: %s", e)


if __name__ == "__main__":
    main()
