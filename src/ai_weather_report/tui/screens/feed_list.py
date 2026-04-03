"""Feed list screen - browse cached articles with filtering."""

from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Input, ListItem, ListView, ProgressBar, Static

from rich.markup import escape as markup_escape

from ai_weather_report import cache


class ArticleListItem(ListItem):
    """A single article row in the feed list."""

    DEFAULT_CSS = """
    ArticleListItem {
        height: 4;
        padding: 0 2;
    }
    """

    def __init__(self, article: dict) -> None:
        super().__init__()
        self.article = article

    def compose(self) -> ComposeResult:
        in_report = bool(self.article.get("reports"))
        indicator = "\u25cf" if in_report else "\u25cb"
        indicator_color = "$success" if in_report else "$text-disabled"

        pub = self.article.get("published", "")
        if pub:
            try:
                dt = datetime.fromisoformat(pub)
                date_str = dt.strftime("%b %d")
            except ValueError:
                date_str = pub[:10]
        else:
            date_str = "     "

        source = markup_escape(self.article.get("source", ""))
        title = markup_escape(self.article.get("title", "Untitled"))
        tags = self.article.get("tags", [])
        tag_str = "  ".join(f"\\[{markup_escape(t)}]" for t in tags[:3]) if tags else ""

        title_markup = f"[bold]{title}[/bold]" if in_report else title

        yield Static(
            f"[{indicator_color}]{indicator}[/]  {title_markup}\n"
            f"    [dim]{date_str}  \u2022  {source}[/]\n"
            f"    [dim italic]{tag_str}[/]",
        )


class FeedListScreen(Screen):
    """Full-screen article feed with filter and update."""

    BINDINGS = [
        Binding("slash", "show_filter", "/Filter", key_display="/"),
        Binding("u", "update_feed", "Update feed"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._articles: list[dict] = []
        self._filtered: list[dict] = []
        self._filter_visible = False
        self._updating = False

    def compose(self) -> ComposeResult:
        yield Static(
            "[b]AI Weather Report[/b]  [dim]- Feed[/dim]",
            id="feed-header",
        )
        yield Input(placeholder="Filter articles...", id="filter-input")
        with Center():
            yield ListView(id="feed-list")
        with Vertical(id="feed-footer"):
            yield Static("", id="feed-progress-label", markup=False)
            yield ProgressBar(id="feed-progress", total=100, show_eta=False)
            yield Static("Loading...", id="feed-status", markup=False)
            yield Static("", id="feed-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#filter-input").display = False
        self.query_one("#feed-progress-label").display = False
        self.query_one("#feed-progress").display = False
        self._load_articles()
        self.query_one("#feed-list", ListView).focus()
        self._update_hint()

    def on_screen_resume(self) -> None:
        self._load_articles()
        self.query_one("#feed-list", ListView).focus()

    def _load_articles(self) -> None:
        self._articles = cache.load_all_articles()
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.query_one("#filter-input", Input).value.strip().lower()
        if query:
            self._filtered = [
                a for a in self._articles
                if query in a.get("title", "").lower()
                or query in a.get("summary", "").lower()
                or any(query in t.lower() for t in a.get("tags", []))
            ]
        else:
            self._filtered = list(self._articles)

        self._rebuild_list()
        self._update_status()

    def _rebuild_list(self) -> None:
        lv = self.query_one("#feed-list", ListView)
        lv.clear()
        for article in self._filtered:
            lv.append(ArticleListItem(article))

    def _update_status(self) -> None:
        total = len(self._articles)
        shown = len(self._filtered)
        in_report = sum(1 for a in self._filtered if a.get("reports"))

        parts = [f"{shown}/{total} articles"]
        if in_report:
            parts.append(f"{in_report} in reports")

        self.query_one("#feed-status", Static).update(" | ".join(parts))

    def _update_hint(self) -> None:
        self.query_one("#feed-hint", Static).update(
            " /  Filter    u  Update feed    Enter  View    Esc  Back    q  Quit"
        )

    def _show_progress(self, label: str, current: int, total: int) -> None:
        """Update progress bar from the main thread."""
        progress_label = self.query_one("#feed-progress-label", Static)
        progress_bar = self.query_one("#feed-progress", ProgressBar)

        progress_label.display = True
        progress_bar.display = True

        progress_label.update(f"  {label}")
        progress_bar.update(total=total, progress=current)

    def _hide_progress(self) -> None:
        self.query_one("#feed-progress-label").display = False
        self.query_one("#feed-progress").display = False

    @on(ListView.Selected, "#feed-list")
    def on_article_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ArticleListItem):
            from ai_weather_report.tui.screens.article_detail import ArticleDetailScreen
            self.app.push_screen(ArticleDetailScreen(event.item.article))

    @on(Input.Changed, "#filter-input")
    def on_filter_changed(self, event: Input.Changed) -> None:
        self._apply_filter()

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            inp = self.query_one("#filter-input", Input)
            if self._filter_visible:
                inp.value = ""
                inp.display = False
                self._filter_visible = False
                self._apply_filter()
                self.query_one("#feed-list", ListView).focus()
            else:
                self.app.pop_screen()

    def action_show_filter(self) -> None:
        inp = self.query_one("#filter-input", Input)
        inp.display = True
        self._filter_visible = True
        inp.focus()

    def action_update_feed(self) -> None:
        if self._updating:
            return
        self._updating = True
        self._show_progress("Fetching feeds...", 0, 100)
        self._do_update()

    @work(thread=True, exclusive=True)
    def _do_update(self) -> None:
        import io
        import sys
        from ai_weather_report.config import (
            get_feeds, get_fetch_days, get_llm_config, get_retention_days,
            load_config,
        )
        from ai_weather_report.pipeline import fetch_feeds, fetch_and_summarise
        from ai_weather_report import cache as cache_mod

        config = load_config()
        llm_cfg = get_llm_config(config)
        feeds = get_feeds(config)
        retention = get_retention_days(config)
        fetch_days = get_fetch_days(config)

        # Step 1: Fetch RSS feeds
        self.app.call_from_thread(
            self._show_progress, "Fetching RSS feeds...", 0, 1
        )

        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            articles = fetch_feeds(feeds, days=fetch_days, max_per_feed=20)
        except Exception:
            sys.stderr = old_stderr
            self.app.call_from_thread(self._finish_update, -1)
            return
        finally:
            sys.stderr = old_stderr

        if not articles:
            self.app.call_from_thread(self._finish_update, 0)
            return

        # Step 2: Fetch article text and summarise with progress
        def on_progress(stage, current, total, detail):
            if stage == "fetch":
                label = f"Fetching article {current + 1}/{total}"
            elif stage == "summarise":
                label = f"Summarising {current + 1}/{total}"
            elif stage == "done":
                label = "Done"
                return
            else:
                return
            self.app.call_from_thread(self._show_progress, label, current + 1, total)

        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            result = fetch_and_summarise(articles, llm_cfg, progress_cb=on_progress)
            # Prune old entries
            cache_mod.prune(retention)
            count = len(result)
        except Exception:
            count = -1
        finally:
            sys.stderr = old_stderr

        self.app.call_from_thread(self._finish_update, count)

    def _finish_update(self, count: int) -> None:
        self._updating = False
        self._hide_progress()
        self._load_articles()
        if count >= 0:
            self.query_one("#feed-status", Static).update(
                f"Updated - {count} articles"
            )
        else:
            self.query_one("#feed-status", Static).update("Update failed")

    def action_back(self) -> None:
        self.app.pop_screen()
