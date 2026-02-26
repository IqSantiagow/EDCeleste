import glob
import os
import time


class JournalWatcherService:

    def __init__(self, journal_path):
        self.journal_path = journal_path

    def follow_journal(self):
        latest_file_path = self.__get_latest_journal_filepath()

        with open(latest_file_path, 'r') as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                yield line

    def __get_latest_journal_filepath(self):
        all_files = glob.glob(self.journal_path + '/*.log')

        journal_files = [f for f in all_files if 'Journal' in f]

        if not journal_files:
            raise FileNotFoundError("No journal files found in the specified directory.")

        latest_file = max(journal_files, key=os.path.getctime)

        return os.path.join(self.journal_path, latest_file)