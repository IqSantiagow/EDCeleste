import unittest

from edceleste.services.models.instinct_status import (
    DownloadProgress,
    describe_download_progress,
    describe_size,
)


class DescribeSizeTest(unittest.TestCase):
    def test_megabytes_below_a_gigabyte(self):
        self.assertEqual(describe_size(630_000_000), "630 MB")

    def test_gigabytes_with_one_decimal(self):
        self.assertEqual(describe_size(1_524_827_608), "1.5 GB")


class DescribeDownloadProgressTest(unittest.TestCase):
    def test_percent_and_both_sizes(self):
        progress = DownloadProgress(bytes_done=630_000_000, bytes_total=1_500_000_000)

        self.assertEqual(describe_download_progress(progress), "42% · 630 MB of 1.5 GB")

    def test_empty_total_does_not_divide_by_zero(self):
        progress = DownloadProgress(bytes_done=0, bytes_total=0)

        self.assertEqual(describe_download_progress(progress), "0% · 0 MB of 0 MB")
