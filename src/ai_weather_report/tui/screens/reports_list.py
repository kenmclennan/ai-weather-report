"""Reports list screen - browse and manage generated reports."""

from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import ListItem, ListView, ProgressBar, Static

from ai_weather_report import reports
from ai_weather_report.config import REPORTS_DIR


class ReportListItem(ListItem):
    """A single report row."""

    DEFAULT_CSS = """
    ReportListItem {
        height: 4;
        padding: 0 2;
    }
    """

    def __init__(self, report: dict) -> None:
        super().__init__()
        self.report = report

    def compose(self) -> ComposeResult:
        report_id = self.report.get("id", "Unknown")
        story_count = self.report.get("story_count", 0)
        article_count = self.report.get("article_count", 0)
        has_audio = bool(self.report.get("audio_file"))
        audio_icon = "\u266b" if has_audio else " "

        try:
            dt = datetime.strptime(report_id, "%Y-%m-%d-%H%M")
            date_str = dt.strftime("%b %d, %Y %I:%M%p")
        except ValueError:
            date_str = report_id

        # Get audio duration
        duration = ""
        if has_audio:
            dur = reports.get_audio_duration(report_id)
            if dur:
                duration = f"  \u2022  {dur}"

        yield Static(
            f" {audio_icon}  {date_str}{duration}\n"
            f"    {story_count} stories from {article_count} articles",
            markup=False,
        )


class ReportsListScreen(Screen):
    """Full-screen reports list."""

    BINDINGS = [
        Binding("g", "generate_report", "Generate report"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._reports: list[dict] = []
        self._generating = False

    def compose(self) -> ComposeResult:
        yield Static(
            "[b]AI Weather Report[/b]  [dim]- Reports[/dim]",
            id="reports-header",
        )
        with Center():
            yield ListView(id="reports-list")
        with Vertical(id="reports-footer"):
            yield Static("", id="reports-progress-label", markup=False)
            yield ProgressBar(id="reports-progress", total=100, show_eta=False)
            yield Static("Loading...", id="reports-status", markup=False)
            yield Static("", id="reports-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#reports-progress-label").display = False
        self.query_one("#reports-progress").display = False
        self._load_reports()
        self.query_one("#reports-list", ListView).focus()
        self._update_hint()

    def on_screen_resume(self) -> None:
        self._load_reports()
        self.query_one("#reports-list", ListView).focus()

    def _load_reports(self) -> None:
        self._reports = reports.list_reports()
        lv = self.query_one("#reports-list", ListView)
        lv.clear()
        for report in self._reports:
            lv.append(ReportListItem(report))
        self._update_status()

    def _update_status(self) -> None:
        count = len(self._reports)
        self.query_one("#reports-status", Static).update(
            f"{count} report{'s' if count != 1 else ''}"
        )

    def _update_hint(self) -> None:
        self.query_one("#reports-hint", Static).update(
            " g  Generate new report    Enter  View    Esc  Back    q  Quit"
        )

    def _show_progress(self, label: str, current: int, total: int) -> None:
        pl = self.query_one("#reports-progress-label", Static)
        pb = self.query_one("#reports-progress", ProgressBar)
        pl.display = True
        pb.display = True
        pl.update(f"  {label}")
        pb.update(total=total, progress=current)

    def _hide_progress(self) -> None:
        self.query_one("#reports-progress-label").display = False
        self.query_one("#reports-progress").display = False

    @on(ListView.Selected, "#reports-list")
    def on_report_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ReportListItem):
            from ai_weather_report.tui.screens.report_detail import ReportDetailScreen
            self.app.push_screen(ReportDetailScreen(event.item.report))

    def action_generate_report(self) -> None:
        if self._generating:
            return
        self._generating = True
        self._show_progress("Fetching feeds...", 0, 1)
        self._do_generate()

    @work(thread=True, exclusive=True)
    def _do_generate(self) -> None:
        import io
        import sys
        from datetime import datetime, timezone
        from ai_weather_report import cache as cache_mod
        from ai_weather_report import reports as reports_mod
        from ai_weather_report.config import (
            get_feeds, get_fetch_days, get_llm_config, get_retention_days,
            get_tts_config, load_config,
        )
        from ai_weather_report.pipeline import (
            fetch_and_summarise, fetch_feeds, run_report,
        )

        config = load_config()
        llm_cfg = get_llm_config(config)
        tts_cfg = get_tts_config(config)
        feeds = get_feeds(config)
        retention = get_retention_days(config)
        fetch_days = get_fetch_days(config)

        # Step 1: Fetch feeds first
        self.app.call_from_thread(
            self._show_progress, "Fetching RSS feeds...", 0, 1
        )

        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            articles = fetch_feeds(feeds, days=fetch_days, max_per_feed=20)
        except Exception as e:
            sys.stderr = old_stderr
            err = f"Feed fetch failed: {type(e).__name__}: {e}"
            self.app.call_from_thread(self._finish_generate, None, None, err)
            return
        finally:
            sys.stderr = old_stderr

        # Step 2: Summarise new articles
        if articles:
            def on_fetch_progress(stage, current, total, detail):
                if stage == "fetch":
                    label = f"Fetching article {current + 1}/{total}"
                elif stage == "summarise":
                    label = f"Summarising {current + 1}/{total}"
                else:
                    return
                self.app.call_from_thread(
                    self._show_progress, label, current + 1, total
                )

            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            try:
                fetch_and_summarise(articles, llm_cfg, progress_cb=on_fetch_progress)
                cache_mod.prune(retention)
            except Exception:
                pass
            finally:
                sys.stderr = old_stderr

        # Step 3: Generate report from articles since last report
        all_articles = cache_mod.load_all_articles()
        all_articles = [a for a in all_articles if a.get("summary")]

        # Filter to only articles not yet included in any report
        unreported = [a for a in all_articles if not a.get("reports")]
        # Use unreported articles if available, otherwise fall back to all
        report_articles = unreported if unreported else all_articles

        if not report_articles:
            self.app.call_from_thread(
                self._finish_generate, None, None, "No articles available for report"
            )
            return

        # Calculate days span for the editorial prompt
        last_reports = reports_mod.list_reports()
        if last_reports:
            last_created = last_reports[0].get("created_at", "")
            try:
                last_dt = datetime.fromisoformat(last_created)
                days_since = (datetime.now(timezone.utc) - last_dt).days or 1
            except (ValueError, TypeError):
                days_since = fetch_days
        else:
            days_since = fetch_days

        def on_report_progress(stage, current, total, detail):
            if stage == "editorial":
                label = "Running editorial pass..."
            elif stage == "audio":
                label = f"Generating audio {current + 1}/{total}"
            elif stage == "done":
                return
            else:
                label = detail or stage
            self.app.call_from_thread(
                self._show_progress, label, max(current, 0), max(total, 1)
            )

        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            result = run_report(
                report_articles, days=days_since, llm_cfg=llm_cfg,
                tts_cfg=tts_cfg, audio_format="mp3",
                progress_cb=on_report_progress,
            )
            tts_error = result.get("tts_error")
            error_msg = None
        except Exception as e:
            result = None
            tts_error = None
            error_msg = f"{type(e).__name__}: {e}"
        finally:
            sys.stderr = old_stderr

        self.app.call_from_thread(self._finish_generate, result, tts_error, error_msg)

    def _finish_generate(self, result: dict | None, tts_error: str | None,
                         error_msg: str | None = None) -> None:
        self._generating = False
        self._hide_progress()
        self._load_reports()
        if result:
            if tts_error:
                self.app.notify(
                    f"TTS unavailable: {tts_error}\nReport saved without audio.",
                    title="TTS Failed",
                    severity="warning",
                    timeout=10,
                )
                self.query_one("#reports-status", Static).update(
                    f"Report generated (no audio - TTS failed)"
                )
            else:
                self.query_one("#reports-status", Static).update("Report generated")
        else:
            msg = f"Generation failed: {error_msg}" if error_msg else "Generation failed"
            self.query_one("#reports-status", Static).update(msg)
            if error_msg:
                self.app.notify(error_msg, title="Report Failed", severity="error", timeout=15)

    def action_back(self) -> None:
        self.app.pop_screen()
