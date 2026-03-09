import logging

from config.config import load_config
from projection.event_projections.fuel_projection import FuelProjection
from services.journal_watcher import JournalWatcherService


if __name__ == "__main__":
    config = load_config()

    log_level = config.ed.logging.level

    logging.basicConfig(level=getattr(logging, log_level))

    print(config.ed.main_path)
    watcher = JournalWatcherService(config.ed.main_path)

    fuel_projection = FuelProjection()

    for event in watcher.emit_journal_events():
        fuel_projection.process_event(event)
        print(fuel_projection.create_projection())
