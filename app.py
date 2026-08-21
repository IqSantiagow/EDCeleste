import logging

from langchain_core.exceptions import LangChainException
from textual.logging import TextualHandler

from config.config import LangSmithConfig
from config.tracing import configure_langsmith
from containers.main_container import Container
from ui.ui_app import UIApp


if __name__ == "__main__":
    container = Container()
    container.wire(
        modules=[
            "ui.ui_app",
            "ui.screens.settings.widgets.tts.widget_tts_container",
            "ui.screens.settings.widgets.stt.widget_stt_container",
        ]
    )

    log_level = container.config.logging.level()

    logging.basicConfig(level=getattr(logging, log_level), handlers=[TextualHandler()])

    logger = logging.getLogger(__name__)

    configure_langsmith(LangSmithConfig(**container.config.langsmith()))

    try:
        UIApp().run()
    except LangChainException as e:
        logger.error("Raised a Langchain exception: %s", e)
    except Exception as e:
        logger.error("Raised an exception: %s", e)
