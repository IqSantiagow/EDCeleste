from config.config import load_config
from services.journal_watcher import JournalWatcherService

config = load_config()

if __name__ == "__main__":
    print(config.ed.main_path)
    watcher = JournalWatcherService(config.ed.main_path)
    for line in watcher.follow_journal():
        print(line.strip())