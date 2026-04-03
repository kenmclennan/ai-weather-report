"""Report detail screen - view report stories, transcript, links, and play audio."""

import subprocess
from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ai_weather_report import reports
from ai_weather_report.config import REPORTS_DIR


class ReportDetailScreen(Screen):
    """Full-screen report detail with transcript, links, and playback."""

    BINDINGS = [
        Binding("p", "play_audio", "Play audio"),
        Binding("t", "open_transcript", "Open transcript"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, report: dict) -> None:
        super().__init__()
        self.report = report
        self._playing_process: subprocess.Popen | None = None

    def compose(self) -> ComposeResult:
        r = self.report
        report_id = r.get("id", "Unknown")
        story_count = r.get("story_count", 0)
        article_count = r.get("article_count", 0)
        days = r.get("days_back", "?")
        has_audio = bool(r.get("audio_file"))

        try:
            dt = datetime.strptime(report_id, "%Y-%m-%d-%H%M")
            date_str = dt.strftime("%B %d, %Y %I:%M%p")
        except ValueError:
            date_str = report_id

        # Audio duration
        duration_str = ""
        if has_audio:
            dur = reports.get_audio_duration(report_id)
            if dur:
                duration_str = f"  |  Duration: {dur}"

        yield Static(
            "[b]AI Weather Report[/b]  [dim]- Report[/dim]",
            id="report-header",
        )
        with Center():
            with VerticalScroll(id="report-scroll"):
                yield Static(f"Report: {date_str}", id="report-title")
                yield Static(
                    f"{story_count} stories from {article_count} articles  |  "
                    f"Last {days} days  |  "
                    f"Audio: {'yes' if has_audio else 'no'}"
                    f"{duration_str}",
                    id="report-info",
                )
                yield Static("", id="report-spacer")

                # Full transcript
                transcript = self._load_transcript()
                yield Static("TRANSCRIPT", id="report-section-header")
                yield Static("", id="report-spacer2")
                yield Static(transcript, id="report-transcript", markup=False)

                # Source links
                links = self._load_links()
                if links:
                    yield Static("", id="report-spacer3")
                    yield Static("SOURCE LINKS", id="report-links-header")
                    yield Static("", id="report-spacer4")
                    yield Static(links, id="report-links", markup=False)

        yield Static("", id="report-playback", markup=False)
        hints = []
        if has_audio:
            hints.append("p  Play audio")
        hints.extend(["t  Open transcript", "Esc  Back", "q  Quit"])
        yield Static(" " + "    ".join(hints), id="report-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#report-scroll").focus()
        self.query_one("#report-playback").display = False

    def _load_transcript(self) -> str:
        report_id = self.report.get("id", "")
        transcript_path = REPORTS_DIR / report_id / "transcript.txt"
        if not transcript_path.exists():
            return "Transcript not found."
        return transcript_path.read_text().strip()

    def _load_links(self) -> str:
        report_id = self.report.get("id", "")
        links_path = REPORTS_DIR / report_id / "links.md"
        if not links_path.exists():
            return ""
        return links_path.read_text().strip()

    def action_play_audio(self) -> None:
        audio_file = self.report.get("audio_file")
        if not audio_file:
            return

        report_id = self.report["id"]
        audio_path = REPORTS_DIR / report_id / audio_file

        if not audio_path.exists():
            self.query_one("#report-playback", Static).update(
                f"Audio file not found: {audio_path}"
            )
            self.query_one("#report-playback").display = True
            return

        self._start_playback(audio_path, report_id)

    @work(thread=True)
    def _start_playback(self, audio_path: Path, report_id: str) -> None:
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
            self._playing_process.wait()

        self.app.call_from_thread(
            self.query_one("#report-playback", Static).update,
            f"Playing: {report_id}..."
        )
        self.app.call_from_thread(
            setattr, self.query_one("#report-playback"), "display", True
        )

        try:
            self._playing_process = subprocess.Popen(
                ["afplay", str(audio_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._playing_process.wait()
            self.app.call_from_thread(
                self.query_one("#report-playback", Static).update,
                f"Finished: {report_id}"
            )
        except FileNotFoundError:
            self.app.call_from_thread(
                self.query_one("#report-playback", Static).update,
                "Error: afplay not found (macOS only)"
            )

    def action_open_transcript(self) -> None:
        report_id = self.report.get("id", "")
        transcript_path = REPORTS_DIR / report_id / "transcript.txt"
        if transcript_path.exists():
            subprocess.Popen(["open", str(transcript_path)])

    def action_back(self) -> None:
        if self._playing_process and self._playing_process.poll() is None:
            self._playing_process.terminate()
        self.app.pop_screen()
