import logging

from config.config import load_config
from services.journal_watcher import JournalWatcherService


if __name__ == "__main__":
    config = load_config()

    log_level = config.ed.logging.level

    logging.basicConfig(level=getattr(logging, log_level))

    print(config.ed.main_path)
    watcher = JournalWatcherService(config.ed.main_path)

    for event in watcher.emit_journal_events():
        print(event.event)
