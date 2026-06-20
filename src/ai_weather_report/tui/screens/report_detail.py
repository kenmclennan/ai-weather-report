"""Report detail screen - view report stories, transcript, links, and play audio."""

import re
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ai_weather_report import reports
from ai_weather_report.config import REPORTS_DIR, get_tts_config, load_config
from ai_weather_report.pipeline import regenerate_audio
from ai_weather_report.player import MpvPlayer, format_time


class ReportDetailScreen(Screen):
    """Full-screen report detail with transcript, links, and playback controls."""

    BINDINGS = [
        Binding("p", "play_audio", "Play"),
        Binding("space", "toggle_pause", "Pause", key_display="Space"),
        Binding("s", "stop_audio", "Stop"),
        Binding("left", "seek_back", "-10s", key_display="\u2190"),
        Binding("right", "seek_forward", "+10s", key_display="\u2192"),
        Binding("r", "regenerate_audio", "Regen Audio"),
        Binding("t", "open_transcript", "Transcript"),
        Binding("escape", "back", "Back"),
    ]

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, report: dict) -> None:
        super().__init__()
        self.report = report
        self._player = MpvPlayer()
        self._playback_active = False
        self._regenerating = False
        self._regen_status = ""

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

                transcript = self._load_transcript()
                yield Static("TRANSCRIPT", id="report-section-header")
                yield Static("", id="report-spacer2")
                yield Static(transcript, id="report-transcript", markup=False)

                links_text = self._build_links_text()
                if links_text is not None:
                    yield Static("", id="report-spacer3")
                    yield Static("SOURCE LINKS", id="report-links-header")
                    yield Static("", id="report-spacer4")
                    yield Static(links_text, id="report-links")

        yield Static("", id="report-playback", markup=False)
        yield Static("", id="report-hint", markup=False)

    def on_mount(self) -> None:
        self.query_one("#report-scroll").focus()
        self.query_one("#report-playback").display = False
        self._update_hint()

    def _update_hint(self) -> None:
        has_audio = bool(self.report.get("audio_file"))
        if self._playback_active:
            self.query_one("#report-hint", Static).update(
                " Space  Pause    \u2190/\u2192  Skip 10s    s  Stop    t  Transcript    Esc  Back    q  Quit"
            )
        elif self._regenerating:
            self.query_one("#report-hint", Static).update(
                " Regenerating audio...    Esc  Back    q  Quit"
            )
            return
        else:
            hints = []
            if has_audio:
                hints.append("p  Play")
            hints.extend(["r  Regen Audio", "t  Transcript", "Esc  Back", "q  Quit"])
            self.query_one("#report-hint", Static).update(
                " " + "    ".join(hints)
            )

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

    def _build_links_text(self) -> Text | None:
        """Parse links.md and return a Rich Text object with clickable URLs."""
        raw = self._load_links()
        if not raw:
            return None

        text = Text()
        url_pattern = re.compile(r"^\s+(https?://\S+)\s*$")

        for i, line in enumerate(raw.splitlines()):
            if i > 0:
                text.append("\n")

            match = url_pattern.match(line)
            if match:
                url = match.group(1)
                indent = line[: line.index("h")]
                text.append(indent)
                text.append(
                    url,
                    style=f"underline link {url}",
                )
            elif line.startswith("## "):
                text.append(line[3:], style="bold")
            else:
                text.append(line)

        return text

    def action_open_url(self, url: str) -> None:
        """Open a URL in the default browser."""
        webbrowser.open(url)

    # --- Playback controls ---

    def action_play_audio(self) -> None:
        audio_file = self.report.get("audio_file")
        if not audio_file:
            return

        report_id = self.report["id"]
        audio_path = REPORTS_DIR / report_id / audio_file

        if not audio_path.exists():
            self._show_playback(f"Audio file not found")
            return

        self._player.play(audio_path)
        self._playback_active = True
        self._update_hint()
        self._show_playback("Starting...")
        self._poll_playback()

    def action_toggle_pause(self) -> None:
        if self._playback_active:
            self._player.toggle_pause()

    def action_stop_audio(self) -> None:
        if self._playback_active:
            self._player.stop()
            self._playback_active = False
            self.query_one("#report-playback").display = False
            self._update_hint()

    def action_seek_back(self) -> None:
        if self._playback_active:
            self._player.seek(-10)

    def action_seek_forward(self) -> None:
        if self._playback_active:
            self._player.seek(10)

    def _show_playback(self, text: str) -> None:
        pb = self.query_one("#report-playback", Static)
        pb.update(text)
        pb.display = True

    @work(thread=True)
    def _poll_playback(self) -> None:
        """Poll mpv for position updates."""
        import time as _time

        while self._playback_active and self._player.is_running:
            pos = self._player.get_position()
            dur = self._player.get_duration()
            paused = self._player.is_paused()

            pos_str = format_time(pos)
            dur_str = format_time(dur)

            icon = "\u23f8" if paused else "\u25b6"

            # Build progress bar
            bar = ""
            if pos is not None and dur and dur > 0:
                pct = min(pos / dur, 1.0)
                bar_width = 30
                filled = int(pct * bar_width)
                bar = f"  [\u2588" * 0 + "\u2588" * filled + "\u2591" * (bar_width - filled) + "]"

            status = f" {icon}  {pos_str} / {dur_str}{bar}"

            self.app.call_from_thread(self._show_playback, status)
            _time.sleep(0.5)

        # Playback ended
        if self._playback_active:
            self._playback_active = False
            self.app.call_from_thread(self._show_playback, " Playback finished")
            self.app.call_from_thread(self._update_hint)

    def action_regenerate_audio(self) -> None:
        if self._regenerating:
            return
        report_id = self.report.get("id", "")
        transcript_path = REPORTS_DIR / report_id / "transcript.txt"
        if not transcript_path.exists():
            self._show_playback("No transcript found - cannot regenerate")
            return
        self._regenerating = True
        self._regen_status = "Starting audio generation..."
        self._show_playback(self._regen_status)
        self._update_hint()
        self._run_regenerate(report_id)
        self._spin_regenerate()

    @work(thread=True)
    def _spin_regenerate(self) -> None:
        """Animate a spinner while regeneration is in progress."""
        import time as _time
        frame = 0
        while self._regenerating:
            spinner = self.SPINNER_FRAMES[frame % len(self.SPINNER_FRAMES)]
            self.app.call_from_thread(
                self._show_playback,
                f" {spinner} {self._regen_status}")
            frame += 1
            _time.sleep(0.1)

    @work(thread=True)
    def _run_regenerate(self, report_id: str) -> None:
        def progress(stage, current, total, detail):
            if stage == "audio":
                self._regen_status = f"Generating audio chunk {current + 1}/{total}..."

        config = load_config()
        tts_cfg = get_tts_config(config)
        result = regenerate_audio(report_id, tts_cfg, progress_cb=progress)
        self._regenerating = False
        if result.get("tts_error"):
            self.app.call_from_thread(
                self._show_playback, f" TTS failed: {result['tts_error']}")
        else:
            # Reload manifest so play button picks up the new audio file
            updated = reports.load_manifest(report_id)
            if updated:
                self.report = updated
            self.app.call_from_thread(
                self._show_playback, " Audio regenerated successfully")
            self.app.call_from_thread(self._update_hint)

    def action_open_transcript(self) -> None:
        report_id = self.report.get("id", "")
        transcript_path = REPORTS_DIR / report_id / "transcript.txt"
        if transcript_path.exists():
            subprocess.Popen(["open", str(transcript_path)])

    def action_back(self) -> None:
        self._player.stop()
        self._playback_active = False
        self.app.pop_screen()
