"""Feed browser tab - browse cached articles with search and filtering."""

import webbrowser
from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, ListView, ListItem, Static

from ai_weather_report import cache


class ArticleListItem(ListItem):
    """A single article in the list."""

    def __init__(self, article: dict) -> None:
        super().__init__()
        self.article = article

    def compose(self) -> ComposeResult:
        indicator = "\u25cf" if self.article.get("reports") else "\u25cb"
        indicator_class = "article-indicator" if self.article.get("reports") else "article-indicator-unused"

        # Format date
        pub = self.article.get("published", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub)
                date_str = dt.strftime("%b %d")
            except ValueError:
                date_str = pub[:10]
        else:
            date_str = "?"

        source = self.article.get("source", "Unknown")
        title = self.article.get("title", "Untitled")
        tags = self.article.get("tags", [])
        tag_str = " ".join(f"[{t}]" for t in tags[:3]) if tags else ""

        with Horizontal():
            yield Static(indicator, classes=indicator_class)
            with Vertical():
                yield Static(f"{title}", classes="article-title")
                yield Static(f"{date_str} - {source}  {tag_str}", classes="article-meta")


class FeedTab(Widget):
    """Feed browser with article list and detail pane."""

    BINDINGS = [
        Binding("slash", "focus_search", "/Search", key_display="/"),
        Binding("escape", "clear_filter", "Clear filter"),
        Binding("o", "open_article", "Open in browser"),
    ]

    search_query: reactive[str] = reactive("")
    active_tag_filter: reactive[str] = reactive("")
    active_source_filter: reactive[str] = reactive("")

    def __init__(self) -> None:
        super().__init__()
        self._articles: list[dict] = []
        self._filtered: list[dict] = []
        self._selected: dict | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="search-bar"):
            yield Label("Filter:", id="filter-label")
            yield Input(placeholder="Search articles...", id="search-input")
        with Horizontal():
            with VerticalScroll(id="article-list-pane"):
                yield ListView(id="article-list")
            with VerticalScroll(id="article-detail-pane"):
                yield Static("Select an article to view details", id="detail-empty")
                yield Static("", id="detail-title")
                yield Static("", id="detail-summary")
                yield Static("", id="detail-tags")
                yield Static("", id="detail-meta")
                yield Static("", id="detail-reports")
        yield Static("Loading...", id="status-bar")

    def on_mount(self) -> None:
        self._load_articles()
        # Hide detail fields until an article is selected
        self.query_one("#detail-title").display = False
        self.query_one("#detail-summary").display = False
        self.query_one("#detail-tags").display = False
        self.query_one("#detail-meta").display = False
        self.query_one("#detail-reports").display = False

    def _load_articles(self) -> None:
        self._articles = cache.load_all_articles()
        self._apply_filters()

    def _apply_filters(self) -> None:
        filtered = self._articles

        # Text search
        if self.search_query:
            q = self.search_query.lower()
            filtered = [
                a for a in filtered
                if q in a.get("title", "").lower()
                or q in a.get("summary", "").lower()
                or any(q in t.lower() for t in a.get("tags", []))
            ]

        # Tag filter
        if self.active_tag_filter:
            filtered = [
                a for a in filtered
                if self.active_tag_filter in a.get("tags", [])
            ]

        # Source filter
        if self.active_source_filter:
            filtered = [
                a for a in filtered
                if a.get("source", "").lower() == self.active_source_filter.lower()
            ]

        self._filtered = filtered
        self._rebuild_list()
        self._update_status()

    def _rebuild_list(self) -> None:
        list_view = self.query_one("#article-list", ListView)
        list_view.clear()
        for article in self._filtered:
            list_view.append(ArticleListItem(article))

    def _update_status(self) -> None:
        total = len(self._articles)
        shown = len(self._filtered)
        in_report = sum(1 for a in self._filtered if a.get("reports"))
        unused = shown - in_report

        parts = [f"{total} articles"]
        if shown != total:
            parts.append(f"{shown} shown")
        parts.append(f"{in_report} in reports")
        parts.append(f"{unused} unused")

        filters = []
        if self.active_tag_filter:
            filters.append(f"tag:{self.active_tag_filter}")
        if self.active_source_filter:
            filters.append(f"source:{self.active_source_filter}")
        if filters:
            parts.append("Filter: " + ", ".join(filters))

        parts.append("\u25cf=in report")
        self.query_one("#status-bar", Static).update(" | ".join(parts))

    def _show_detail(self, article: dict) -> None:
        self._selected = article

        self.query_one("#detail-empty").display = False
        self.query_one("#detail-title").display = True
        self.query_one("#detail-summary").display = True
        self.query_one("#detail-tags").display = True
        self.query_one("#detail-meta").display = True
        self.query_one("#detail-reports").display = True

        self.query_one("#detail-title", Static).update(article.get("title", "Untitled"))
        self.query_one("#detail-summary", Static).update(article.get("summary", "No summary"))

        tags = article.get("tags", [])
        if tags:
            tag_str = " ".join(f"[{t}]" for t in tags)
            self.query_one("#detail-tags", Static).update(f"Tags: {tag_str}")
        else:
            self.query_one("#detail-tags", Static).update("")

        # Metadata
        pub = article.get("published", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub)
                pub_str = dt.strftime("%B %d, %Y %I:%M%p")
            except ValueError:
                pub_str = pub
        else:
            pub_str = "Unknown"

        source = article.get("source", "Unknown")
        meta_lines = [
            f"Source: {source}",
            f"Published: {pub_str}",
        ]
        url = article.get("url", "")
        if url:
            meta_lines.append(f"URL: {url}")
        self.query_one("#detail-meta", Static).update("\n".join(meta_lines))

        # Reports
        reports = article.get("reports", [])
        if reports:
            self.query_one("#detail-reports", Static).update(
                f"Reports: {', '.join(reports)}"
            )
        else:
            self.query_one("#detail-reports", Static).update("Not included in any report")

    @on(ListView.Selected, "#article-list")
    def on_article_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ArticleListItem):
            self._show_detail(event.item.article)

    @on(ListView.Highlighted, "#article-list")
    def on_article_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, ArticleListItem):
            self._show_detail(event.item.article)

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self.search_query = event.value
        self._apply_filters()

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_clear_filter(self) -> None:
        self.query_one("#search-input", Input).value = ""
        self.search_query = ""
        self.active_tag_filter = ""
        self.active_source_filter = ""
        self._apply_filters()

    def action_open_article(self) -> None:
        if self._selected and self._selected.get("url"):
            webbrowser.open(self._selected["url"])

    def refresh_data(self) -> None:
        """Reload articles from cache."""
        self._load_articles()
