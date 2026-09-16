import unittest

from edceleste.services.models.rank_ladders import (
    EXPLORATION_RANKS,
    UNKNOWN_RANK,
    rank_name,
)


class TestRankLadders(unittest.TestCase):
    def test_rank_name_returns_ladder_entry_for_known_number(self):
        self.assertEqual(rank_name(EXPLORATION_RANKS, 5), "Pathfinder")

    def test_rank_name_returns_first_entry_for_zero(self):
        self.assertEqual(rank_name(EXPLORATION_RANKS, 0), "Aimless")

    def test_rank_name_returns_unranked_for_number_out_of_range(self):
        self.assertEqual(rank_name(EXPLORATION_RANKS, 99), UNKNOWN_RANK)

    def test_rank_name_returns_unranked_for_none(self):
        self.assertEqual(rank_name(EXPLORATION_RANKS, None), UNKNOWN_RANK)


if __name__ == "__main__":
    unittest.main()
