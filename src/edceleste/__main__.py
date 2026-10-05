import logging

from textual.logging import TextualHandler

from edceleste.config.config import AppConfig
from edceleste.containers.main_container import MODULES_USING_PROVIDE, Container
from edceleste.ui.ui_app import UIApp


def main() -> None:
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
