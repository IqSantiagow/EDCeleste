import unittest

from edceleste.services.models.market_stats import MarketSnapshot
from edceleste.ui.screens.dashboard.view_models.station_market_view_model import (
    MAX_BLOCKS,
    NO_MARKET_MESSAGE,
    NO_STATION_MESSAGE,
    STALE_MARKET_MESSAGE,
    StationMarketRowViewModel,
    StationMarketViewModel,
    vs_galactic_average_bar,
)
from tests.projection.test_market_projection import make_market_item

BAR_WIDTH = MAX_BLOCKS * 2 + 1


def make_snapshot(**overrides) -> MarketSnapshot:
    defaults = dict(
        station_name="Fan Horizons",
        is_docked=True,
        has_commodities_market=True,
        is_market_data_current=True,
        commodities=(make_market_item(),),
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


class TestStationMarketViewModelStates(unittest.TestCase):
    def test_shows_a_no_station_message_when_not_docked(self):
        view_model = StationMarketViewModel.from_snapshot(
            make_snapshot(is_docked=False)
        )

        self.assertEqual(view_model.message, NO_STATION_MESSAGE)
        self.assertEqual(view_model.rows, ())

    def test_shows_a_no_market_message_when_the_station_has_no_commodities(self):
        view_model = StationMarketViewModel.from_snapshot(
            make_snapshot(has_commodities_market=False)
        )

        self.assertEqual(view_model.message, NO_MARKET_MESSAGE)
        self.assertEqual(view_model.rows, ())

    def test_shows_an_open_the_market_message_when_the_file_is_stale(self):
        view_model = StationMarketViewModel.from_snapshot(
            make_snapshot(is_market_data_current=False)
        )

        self.assertEqual(view_model.message, STALE_MARKET_MESSAGE)
        self.assertEqual(view_model.rows, ())

    def test_has_no_message_and_one_row_per_commodity_when_data_is_current(self):
        view_model = StationMarketViewModel.from_snapshot(
            make_snapshot(
                commodities=(make_market_item(), make_market_item(Name="$gold_name;"))
            )
        )

        self.assertEqual(view_model.message, "")
        self.assertEqual(len(view_model.rows), 2)

    def test_names_the_station_and_the_commodity_count_in_the_header(self):
        view_model = StationMarketViewModel.from_snapshot(make_snapshot())

        self.assertEqual(view_model.header, "FAN HORIZONS · 1 COMMODITIES")


class TestVsGalacticAverageBar(unittest.TestCase):
    def test_a_price_at_the_galactic_average_is_just_the_zero_axis(self):
        self.assertEqual(vs_galactic_average_bar(1000, 1000).strip(), "▏")

    def test_one_block_grows_right_for_every_three_percent_above_average(self):
        # 1090 is 9% over 1000, so three blocks to the right of the axis.
        self.assertEqual(vs_galactic_average_bar(1090, 1000).strip(), "▏███")

    def test_blocks_grow_left_when_the_price_is_below_the_average(self):
        self.assertEqual(vs_galactic_average_bar(910, 1000).strip(), "███▏")

    def test_the_bar_stops_at_ten_blocks(self):
        # Platinum in the dev fixture sells at +113% of its galactic average.
        self.assertEqual(
            vs_galactic_average_bar(42220, 19756).strip(), "▏" + "█" * MAX_BLOCKS
        )

    def test_the_bar_is_empty_when_the_galactic_average_is_unknown(self):
        self.assertEqual(vs_galactic_average_bar(1000, 0).strip(), "▏")

    def test_the_bar_is_empty_when_the_station_does_not_buy_the_goods(self):
        self.assertEqual(vs_galactic_average_bar(0, 1000).strip(), "▏")

    def test_the_zero_axis_sits_in_the_same_column_for_every_bar(self):
        for price in (0, 500, 1000, 1090, 99999):
            with self.subTest(price=price):
                bar = vs_galactic_average_bar(price, 1000)
                self.assertEqual(len(bar), BAR_WIDTH)
                self.assertEqual(bar.index("▏"), MAX_BLOCKS)


class TestStationMarketRow(unittest.TestCase):
    def test_zero_prices_are_shown_as_a_dash(self):
        row = StationMarketRowViewModel.from_item(make_market_item(BuyPrice=0, Stock=0))

        self.assertEqual(row.buy, "-")
        self.assertEqual(row.stock, "-")

    def test_prices_use_thousand_separators(self):
        row = StationMarketRowViewModel.from_item(make_market_item(SellPrice=42220))

        self.assertEqual(row.sell, "42 220")

    def test_delta_per_tonne_is_signed(self):
        above = StationMarketRowViewModel.from_item(
            make_market_item(SellPrice=42220, MeanPrice=19756)
        )
        below = StationMarketRowViewModel.from_item(
            make_market_item(SellPrice=46990, MeanPrice=47350)
        )

        self.assertEqual(above.delta, "+22 464")
        self.assertEqual(below.delta, "-360")

    def test_delta_is_a_dash_when_the_price_matches_the_average(self):
        row = StationMarketRowViewModel.from_item(
            make_market_item(SellPrice=1000, MeanPrice=1000)
        )

        self.assertEqual(row.delta, "-")

    def test_uses_the_localised_commodity_name_when_the_game_provides_one(self):
        row = StationMarketRowViewModel.from_item(make_market_item())

        self.assertEqual(row.commodity, "Platinum")

    def test_falls_back_to_the_raw_name_when_there_is_no_localised_one(self):
        row = StationMarketRowViewModel.from_item(
            make_market_item(Name="Gold", Name_Localised=None)
        )

        self.assertEqual(row.commodity, "Gold")

    def test_the_note_names_the_demand_bracket(self):
        row = StationMarketRowViewModel.from_item(
            make_market_item(DemandBracket=3, StockBracket=0)
        )

        self.assertEqual(row.note, "high demand")

    def test_the_note_names_the_stock_bracket_when_there_is_no_demand(self):
        row = StationMarketRowViewModel.from_item(
            make_market_item(DemandBracket=0, StockBracket=3)
        )

        self.assertEqual(row.note, "high stock")

    def test_the_note_marks_rare_commodities(self):
        row = StationMarketRowViewModel.from_item(
            make_market_item(DemandBracket=3, Rare=True)
        )

        self.assertEqual(row.note, "high demand · rare")

    def test_the_note_is_a_dash_when_there_is_nothing_to_say(self):
        row = StationMarketRowViewModel.from_item(
            make_market_item(DemandBracket=0, StockBracket=0)
        )

        self.assertEqual(row.note, "-")


if __name__ == "__main__":
    unittest.main()
