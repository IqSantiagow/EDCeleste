import logging
import os

from config.config import LangSmithConfig

logger = logging.getLogger(__name__)


def configure_langsmith(config: LangSmithConfig) -> None:
    if not config.tracing:
        logger.info("LangSmith tracing disabled")
        return

    logger.info("LangSmith tracing enabled for project %s", config.project)

    os.environ["LANGSMITH_TRACING"] = str(config.tracing)
    os.environ["LANGSMITH_API_KEY"] = config.api_key
    os.environ["LANGSMITH_PROJECT"] = config.project
    os.environ["LANGSMITH_ENDPOINT"] = config.endpoint
