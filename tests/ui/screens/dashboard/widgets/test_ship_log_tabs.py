import unittest

from edceleste.ui.screens.dashboard.widgets.ship_log.ship_log_tabs import (
    ALWAYS_EXPANDED_TABS,
    SHIP_LOG_PLACEHOLDER_TABS,
)


class TestShipLogTabsCatalog(unittest.TestCase):
    def test_every_always_expanded_card_is_in_the_catalog(self):
        """Both journal panels are kept on the same card, and Tabs.validate_active
        raises for an id no panel has. Dropping one of these from the catalog
        would crash the app the moment the card is selected."""
        catalog_tab_ids = [tab_id for _, tab_id in SHIP_LOG_PLACEHOLDER_TABS]

        for tab_id in ALWAYS_EXPANDED_TABS:
            with self.subTest(tab_id=tab_id):
                self.assertIn(tab_id, catalog_tab_ids)


if __name__ == "__main__":
    unittest.main()
