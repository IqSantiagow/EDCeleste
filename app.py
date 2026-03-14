import logging

from config.config import load_config
from services.event_bus import EventBus
from services.journal_watcher import JournalWatcherService

if __name__ == "__main__":
    config = load_config()

    log_level = config.ed.logging.level

    logging.basicConfig(level=getattr(logging, log_level))

    print(config.ed.main_path)

    event_bus = EventBus()

    watcher = JournalWatcherService(config.ed.main_path, event_bus)

    watcher.start_watcher_service()
