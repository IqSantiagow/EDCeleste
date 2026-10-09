from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, TabPane

SHIP_LOG_TAB_LOG = "ship-log-tab-log"
SHIP_LOG_TAB_STATION = "ship-log-tab-stn"

# The other cockpit cards. Each one gets its own content in due course;
# for now they show a placeholder.
SHIP_LOG_PLACEHOLDER_TABS = (
    ("SHIP", "ship-log-tab-ship"),
    ("ENG", "ship-log-tab-eng"),
    ("STN", SHIP_LOG_TAB_STATION),
    ("SYS", "ship-log-tab-sys"),
    ("NAV", "ship-log-tab-nav"),
    ("LDG", "ship-log-tab-ldg"),
)

ALWAYS_EXPANDED_TABS = (SHIP_LOG_TAB_STATION,)


def compose_placeholder_tab_panes(
    real_cards: dict[str, Widget] | None = None,
) -> ComposeResult:
    """Yields one TabPane for every card in SHIP_LOG_PLACEHOLDER_TABS, in that
    order. real_cards maps a tab id to the widget that card already has, e.g.
    the station market. A tab without a real card gets a "NO DATA" label.
    None or an empty dict means every tab is a placeholder."""
    real_cards = real_cards or {}
    for tab_title, tab_id in SHIP_LOG_PLACEHOLDER_TABS:
        content = real_cards.get(tab_id) or Label("NO DATA", classes="ship-log-no-data")
        yield TabPane(tab_title, content, id=tab_id)
