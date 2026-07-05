import logging
from langchain_core.exceptions import LangChainException

from config.config import load_config
from config.tracing import configure_langsmith
from ui.ui_app import UIApp
from containers.main_container import Container
from textual.logging import TextualHandler


if __name__ == "__main__":
    container = Container()
    container.wire(
        modules=[
            "ui.ui_app",
            "ui.widgets.dashboard.dashboard_headers.dashboard_stats_content",
        ]
    )

    log_level = container.config.ed.logging.level()

    logging.basicConfig(level=getattr(logging, log_level), handlers=[TextualHandler()])

    logger = logging.getLogger(__name__)

    configure_langsmith(load_config().langsmith)

    try:
        UIApp().run()
    except LangChainException as e:
        logger.error("Raised a Langchain exception: %s", e)
    except Exception as e:
        logger.error("Raised an exception: %s", e)
