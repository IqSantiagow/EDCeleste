import logging

from langchain_core.exceptions import LangChainException
from textual.logging import TextualHandler

from edceleste.config.config import LangSmithConfig
from edceleste.config.tracing import configure_langsmith
from edceleste.containers.main_container import Container
from edceleste.ui.ui_app import UIApp


def main() -> None:
    container = Container()
    container.wire(
        modules=[
            "edceleste.ui.ui_app",
            "edceleste.ui.screens.settings.widgets.tts.widget_edge_tts_settings_vertical",
            "edceleste.ui.screens.settings.widgets.tts.widget_chatterbox_tts_settings_vertical",  # noqa: E501
            "edceleste.ui.screens.settings.widgets.stt.widget_stt_container",
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


if __name__ == "__main__":
    main()
