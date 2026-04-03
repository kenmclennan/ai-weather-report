"""Reports tab - browse and play generated reports."""

import subprocess
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ListView, ListItem, Static

from ai_weather_report import reports
from ai_weather_report.config import REPORTS_DIR


class ReportListItem(ListItem):
    """A single report in the list."""

    def __init__(self, report: dict) -> None:
        super().__init__()
        self.report = report

    def compose(self) -> ComposeResult:
        report_id = self.report.get("id", "Unknown")
        story_count = self.report.get("story_count", 0)
        has_audio = bool(self.report.get("audio_file"))
        audio_icon = "\u266b" if has_audio else " "

        # Parse the report ID as a date
        try:
            dt = datetime.strptime(report_id, "%Y-%m-%d-%H%M")
            date_str = dt.strftime("%b %d, %Y %I:%M%p")
        except ValueError:
            date_str = report_id

        with Vertical():
            yield Static(f"{audio_icon} {date_str}", classes="report-title")
            yield Static(f"  {story_count} stories", classes="report-meta")


class ReportsTab(Widget):
    """Reports browser with list and detail pane."""

    BINDINGS = [
        Binding("p", "play_report", "Play audio"),
        Binding("t", "open_transcript", "Open transcript"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._reports: list[dict] = []
        self._selected: dict | None = None
        self._playing_process: subprocess.Popen | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with VerticalScroll(id="report-list-pane"):
                yield ListView(id="report-list")
            with VerticalScroll(id="report-detail-pane"):
                yield Static("Select a report to view details", id="report-detail-empty")
                yield Static("", id="report-detail-title")
                yield Static("", id="report-detail-info")
                yield Static("", id="report-detail-stories")
        yield Static("", id="playback-bar")
        yield Static("Loading...", id="report-status-bar")

    def on_mount(self) -> None:
        self._load_reports()
        self.query_one("#report-detail-title").display = False
        self.query_one("#report-detail-info").display = False
        self.query_one("#report-detail-stories").display = False
        self.query_one("#playback-bar").display = False

    def _load_reports(self) -> None:
        self._reports = reports.list_reports()
        self._rebuild_list()
        self._update_status()

    def _rebuild_list(self) -> None:
        list_view = self.query_one("#report-list", ListView)
        list_view.clear()
        for report in self._reports:
            list_view.append(ReportListItem(report))

    def _update_status(self) -> None:
        count = len(self._reports)
        status = f"{count} report{'s' if count != 1 else ''}"
        self.query_one("#report-status-bar", Static).update(status)

    def _show_detail(self, report: dict) -> None:
        self._selected = report

        self.query_one("#report-detail-empty").display = False
        self.query_one("#report-detail-title").display = True
        self.query_one("#report-detail-info").display = True
        self.query_one("#report-detail-stories").display = True

        report_id = report.get("id", "Unknown")
        try:
            dt = datetime.strptime(report_id, "%Y-%m-%d-%H%M")
            date_str = dt.strftime("%B %d, %Y %I:%M%p")
        except ValueError:
            date_str = report_id

        self.query_one("#report-detail-title", Static).update(
            f"Report: {date_str}"
        )

        story_count = report.get("story_count", 0)
        article_count = report.get("article_count", 0)
        days = report.get("days_back", "?")
        has_audio = bool(report.get("audio_file"))
        audio_str = report.get("audio_file", "none")

        info_lines = [
            f"{story_count} stories from {article_count} articles",
            f"Looking back: {days} days",
            f"Audio: {audio_str}",
        ]
        self.query_one("#report-detail-info", Static).update("\n".join(info_lines))

        # Load transcript to show story headlines
        report_dir = REPORTS_DIR / report_id
        transcript_path = report_dir / "transcript.txt"
        if transcript_path.exists():
            transcript = transcript_path.read_text()
            # Extract story headlines (lines that don't start with "From" or "That's" or "The AI Weather")
            lines = transcript.strip().split("\n")
            stories = []
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                # Headlines are followed by "From <source>" lines
                if (i + 1 < len(lines)
                        and lines[i + 1].strip().startswith("From ")
                        and not line.startswith("The AI Weather")
                        and not line.startswith("That's")):
                    stories.append(line)

            if stories:
                story_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(stories))
                self.query_one("#report-detail-stories", Static).update(
                    f"Stories:\n{story_text}\n\n[p] Play  [t] Open transcript"
                )
            else:
                self.query_one("#report-detail-stories", Static).update(
                    "Could not parse stories from transcript"
                )
        else:
            self.query_one("#report-detail-stories", Static).update(
                "Transcript not found"
            )

    @on(ListView.Highlighted, "#report-list")
    def on_report_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, ReportListItem):
            self._show_detail(event.item.report)

    @on(ListView.Selected, "#report-list")
    def on_report_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ReportListItem):
            self._show_detail(event.item.report)

    def action_play_report(self) -> None:
        if not self._selected:
            return
        audio_file = self._selected.get("audio_file")
        if not audio_file:
            self.query_one("#playback-bar", Static).update("No audio for this report")
            self.query_one("#playback-bar").display = True
            return

        report_id = self._selected["id"]
        audio_path = REPORTS_DIR / report_id / audio_file

        if not audio_path.exists():
            self.query_one("#playback-bar", Static).update(f"Audio file not found: {audio_path}")
            self.query_one("#playback-bar").display = True
            return

        self._start_playback(audio_path, report_id)

    @work(thread=True)
    def _start_playback(self, audio_path: Path, report_id: str) -> None:
        # Stop any existing playback
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
            self._playing_process.wait()

        self.app.call_from_thread(
            self.query_one("#playback-bar", Static).update,
            f"Playing: {report_id}..."
        )
        self.app.call_from_thread(
            setattr, self.query_one("#playback-bar"), "display", True
        )

        try:
            self._playing_process = subprocess.Popen(
                ["afplay", str(audio_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._playing_process.wait()
            self.app.call_from_thread(
                self.query_one("#playback-bar", Static).update,
                f"Finished: {report_id}"
            )
        except FileNotFoundError:
            self.app.call_from_thread(
                self.query_one("#playback-bar", Static).update,
                "Error: afplay not found (macOS only)"
            )
        except Exception as e:
            self.app.call_from_thread(
                self.query_one("#playback-bar", Static).update,
                f"Error: {e}"
            )

    def action_open_transcript(self) -> None:
        if not self._selected:
            return
        report_id = self._selected["id"]
        transcript_path = REPORTS_DIR / report_id / "transcript.txt"
        if transcript_path.exists():
            subprocess.Popen(["open", str(transcript_path)])

    def refresh_data(self) -> None:
        """Reload reports."""
        self._load_reports()
