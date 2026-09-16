from textual.app import ComposeResult
from textual.widgets import Label, TabPane

SHIP_LOG_TAB_LOG = "ship-log-tab-log"

# The other cockpit cards. Each one gets its own content in due course;
# for now they show a placeholder.
SHIP_LOG_PLACEHOLDER_TABS = (
    ("SHIP", "ship-log-tab-ship"),
    ("ENG", "ship-log-tab-eng"),
    ("STN", "ship-log-tab-stn"),
    ("SYS", "ship-log-tab-sys"),
    ("NAV", "ship-log-tab-nav"),
    ("LDG", "ship-log-tab-ldg"),
)


def compose_placeholder_tab_panes() -> ComposeResult:
    for tab_title, tab_id in SHIP_LOG_PLACEHOLDER_TABS:
        yield TabPane(
            tab_title,
            Label("NO DATA", classes="ship-log-no-data"),
            id=tab_id,
        )
