"""Reports list screen - browse and manage generated reports."""

from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import ListItem, ListView, Static

from ai_weather_report import reports


class ReportListItem(ListItem):
    """A single report row."""

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

        yield Static(
            f" {audio_icon}  {date_str}    {story_count} stories from {article_count} articles",
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

    def compose(self) -> ComposeResult:
        yield Static(
            "[b]AI Weather Report[/b]  [dim]- Reports[/dim]",
            id="reports-header",
        )
        with Center():
            yield ListView(id="reports-list")
        with Vertical(id="reports-footer"):
            yield Static("Loading...", id="reports-status", markup=False)
            yield Static("", id="reports-hint", markup=False)

    def on_mount(self) -> None:
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
            " g  Generate new report    Enter  View    Esc  Back"
        )

    @on(ListView.Selected, "#reports-list")
    def on_report_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ReportListItem):
            from ai_weather_report.tui.screens.report_detail import ReportDetailScreen
            self.app.push_screen(ReportDetailScreen(event.item.report))

    def action_generate_report(self) -> None:
        self.query_one("#reports-status", Static).update("Generating report...")
        self._do_generate()

    @work(thread=True)
    def _do_generate(self) -> None:
        import io
        import sys
        from ai_weather_report import cache as cache_mod
        from ai_weather_report.config import (
            get_llm_config, get_tts_config, load_config,
        )
        from ai_weather_report.pipeline import run_report

        config = load_config()
        llm_cfg = get_llm_config(config)
        tts_cfg = get_tts_config(config)

        all_articles = cache_mod.load_all_articles()
        all_articles = [a for a in all_articles if a.get("summary")]

        if not all_articles:
            self.app.call_from_thread(
                self.query_one("#reports-status", Static).update,
                "No cached articles. Run feed update first."
            )
            return

        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            report_id = run_report(
                all_articles, days=3, llm_cfg=llm_cfg,
                tts_cfg=tts_cfg, audio_format="mp3",
            )
            success = True
        except Exception:
            report_id = None
            success = False
        finally:
            sys.stderr = old_stderr

        def finish():
            self._load_reports()
            if success:
                self.query_one("#reports-status", Static).update(
                    f"Generated report: {report_id}"
                )
            else:
                self.query_one("#reports-status", Static).update(
                    "Report generation failed"
                )

        self.app.call_from_thread(finish)

    def action_back(self) -> None:
        self.app.pop_screen()
