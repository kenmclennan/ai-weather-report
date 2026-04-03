"""Main TUI application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from ai_weather_report.tui.feed_tab import FeedTab
from ai_weather_report.tui.reports_tab import ReportsTab


class WeatherReportApp(App):
    """AI Weather Report TUI."""

    TITLE = "AI Weather Report"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("f", "focus_tab('feed')", "Feed", show=False),
        Binding("r", "focus_tab('reports')", "Reports", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Feed", id="feed"):
                yield FeedTab()
            with TabPane("Reports", id="reports"):
                yield ReportsTab()
        yield Footer()

    def action_focus_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id
