import logging
import threading

from langchain_core.exceptions import LangChainException

from config.config import load_config
from projection.game_state import GameState
from services.event_bus import EventBus
from services.journal_watcher import JournalWatcherService
from services.llm_service import LLMService

if __name__ == "__main__":
    config = load_config()

    log_level = config.ed.logging.level

    logging.basicConfig(level=getattr(logging, log_level))

    logger = logging.getLogger(__name__)

    event_bus = EventBus()

    watcher = JournalWatcherService(config.ed.main_path, event_bus)

    game_state = GameState(event_bus=event_bus)

    watcher_thread = threading.Thread(target=watcher.start_watcher_service, daemon=True)

    watcher_thread.start()

    llm_service = LLMService(
        game_state=game_state, api_key=config.llm.anthropic_api_key
    )

    while True:
        try:
            command = input("Input your LLM query")
            response = llm_service.send_and_receive_message(command)
            print(response)
        except KeyboardInterrupt:
            watcher.stop_watcher_service()
            break
        except LangChainException as e:
            logger.error("Raised a Langchain exception: %s", e)
