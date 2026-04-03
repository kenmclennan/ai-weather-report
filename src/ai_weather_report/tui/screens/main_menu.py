"""Main menu screen - ASCII art title and navigation options."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Middle
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

TITLE_ART = r"""
     _    ___  __        __         _   _
    / \  |_ _| \ \      / /__  __ _| |_| |__   ___ _ __
   / _ \  | |   \ \ /\ / / _ \/ _` | __| '_ \ / _ \ '__|
  / ___ \ | |    \ V  V /  __/ (_| | |_| | | |  __/ |
 /_/   \_\___|    \_/\_/ \___|\__,_|\__|_| |_|\___|_|
                  ____                       _
                 |  _ \ ___ _ __   ___  _ __| |_
                 | |_) / _ \ '_ \ / _ \| '__| __|
                 |  _ <  __/ |_) | (_) | |  | |_
                 |_| \_\___| .__/ \___/|_|   \__|
                           |_|
"""

MENU_OPTIONS = [
    ("feed", "Feed"),
    ("reports", "Weather Reports"),
    ("config", "Config"),
]


class MainMenuScreen(Screen):
    """Home screen with ASCII title and menu."""

    BINDINGS = [
        Binding("q", "quit_app", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        with Middle():
            with Center():
                yield Static(TITLE_ART, id="ascii-title")
            with Center():
                yield OptionList(
                    *[Option(label, id=oid) for oid, label in MENU_OPTIONS],
                    id="menu-options",
                )

    def on_mount(self) -> None:
        self.query_one("#menu-options", OptionList).focus()

    def on_screen_resume(self) -> None:
        self.query_one("#menu-options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id == "feed":
            from ai_weather_report.tui.screens.feed_list import FeedListScreen
            self.app.push_screen(FeedListScreen())
        elif option_id == "reports":
            from ai_weather_report.tui.screens.reports_list import ReportsListScreen
            self.app.push_screen(ReportsListScreen())
        elif option_id == "config":
            from ai_weather_report.config import print_config
            # For now, just show config in a notification
            import subprocess
            from ai_weather_report.config import CONFIG_PATH
            subprocess.Popen(["open", str(CONFIG_PATH)])

    def action_quit_app(self) -> None:
        self.app.exit()
