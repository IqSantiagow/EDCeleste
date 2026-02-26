import unittest
from unittest.mock import patch, mock_open, MagicMock

from services.journal_watcher import JournalWatcherService


class MyTestCase(unittest.TestCase):

    @patch('services.journal_watcher.glob.glob')
    @patch('services.journal_watcher.os.path.getctime')
    def test_get_latest_journal_filepath(self, mock_getctime, mock_glob):

        mock_glob.return_value = [
            'C:/journals/Journal.2024-01-01.log',
            'C:/journals/Journal.2024-01-02.log',
        ]

        mock_getctime.side_effect = [100,200] #getCtime is called for every file that is why it has to be iterable, not array, and we use side_effect

        watcher = JournalWatcherService('C:/journals')

        result = watcher._JournalWatcherService__get_latest_journal_filepath()

        self.assertEqual(result, 'C:/journals/Journal.2024-01-02.log')

    @patch('services.journal_watcher.glob.glob')
    def test_no_journal_files_raises_error(self, mock_glob):
        mock_glob.return_value=[]

        watcher = JournalWatcherService('C:/journals')

        with self.assertRaises(FileNotFoundError):
            watcher._JournalWatcherService__get_latest_journal_filepath()

    @patch('services.journal_watcher.glob.glob')
    @patch('services.journal_watcher.os.path.getctime')
    def test_follow_journal_lines(self,mock_getctime, mock_glob):
        mock_glob.return_value = ['C:/journals/Journal.log']
        mock_getctime.return_value = 100

        with patch('builtins.open', mock_open()) as m:
            #By creating mock object we call open() function
            mock_open_file = m()

            mock_open_file.readline.side_effect = [
            '{"event": "Startup"}\n',
            '{"event": "LoadGame"}\n',
        ]
            watcher = JournalWatcherService('C:/journals')

            gen = watcher.follow_journal()

            self.assertEqual(next(gen), '{"event": "Startup"}\n')
            self.assertEqual(next(gen), '{"event": "LoadGame"}\n')



if __name__ == '__main__':
    unittest.main()
