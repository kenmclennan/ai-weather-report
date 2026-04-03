"""Article detail screen - full article view."""

import webbrowser
from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static


class ArticleDetailScreen(Screen):
    """Full-screen article detail view."""

    BINDINGS = [
        Binding("o", "open_browser", "Open in browser"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, article: dict) -> None:
        super().__init__()
        self.article = article

    def compose(self) -> ComposeResult:
        a = self.article

        pub = a.get("published", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub)
                pub_str = dt.strftime("%B %d, %Y %I:%M%p")
            except ValueError:
                pub_str = pub
        else:
            pub_str = "Unknown date"

        source = a.get("source", "Unknown")
        tags = a.get("tags", [])
        tag_str = "  ".join(f"[{t}]" for t in tags) if tags else "none"
        article_reports = a.get("reports", [])
        report_str = ", ".join(article_reports) if article_reports else "Not included in any report"
        url = a.get("url", "")

        yield Static(
            "[b]AI Weather Report[/b]  [dim]- Article[/dim]",
            id="article-header",
        )
        with Center():
            with VerticalScroll(id="article-scroll"):
                yield Static(a.get("title", "Untitled"), id="article-title", markup=False)
                yield Static(f"{source}  |  {pub_str}", id="article-source", markup=False)
                yield Static("", id="article-spacer")
                yield Static(a.get("summary", "No summary available."), id="article-summary", markup=False)
                yield Static("", id="article-spacer2")
                yield Static(f"Tags: {tag_str}", id="article-tags", markup=False)
                yield Static(f"Reports: {report_str}", id="article-reports", markup=False)
                if url:
                    yield Static(f"URL: {url}", id="article-url", markup=False)

        yield Static(" o  Open in browser    Esc  Back", id="article-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#article-scroll").focus()

    def action_open_browser(self) -> None:
        url = self.article.get("url", "")
        if url:
            webbrowser.open(url)

    def action_back(self) -> None:
        self.app.pop_screen()
