"""Main TUI application - thin shell that pushes MainMenu."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer

from ai_weather_report.tui.screens.main_menu import MainMenuScreen


class WeatherReportApp(App):
    """AI Weather Report TUI."""

    TITLE = "AI Weather Report"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Footer()

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())
