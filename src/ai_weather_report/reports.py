"""Report manifest - track generated reports and their contents."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_weather_report.config import REPORTS_DIR


def report_dir(report_id: str) -> Path:
    """Get the directory for a report."""
    return REPORTS_DIR / report_id


def parse_report_headlines(links_md: str) -> list[str]:
    """Extract the story headlines (## headings) from a links.md body."""
    headlines = []
    for line in links_md.splitlines():
        if line.startswith("## "):
            headline = line[3:].strip()
            if headline:
                headlines.append(headline)
    return headlines


def recent_report_headlines(within_days: int) -> list[str]:
    """Headlines from reports created within the last `within_days` days.

    Reads each recent report's links.md, parses its headings, and returns a
    de-duplicated list (preserving first-seen order). Used to tell the editorial
    pass which events have already been covered.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=within_days)
    seen = set()
    headlines = []
    for report in list_reports():
        created = report.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created)
        except (ValueError, TypeError):
            continue
        if created_dt < cutoff:
            continue
        links_path = report_dir(report["id"]) / "links.md"
        if not links_path.exists():
            continue
        for headline in parse_report_headlines(links_path.read_text()):
            if headline not in seen:
                seen.add(headline)
                headlines.append(headline)
    return headlines


def save_manifest(report_id: str, articles_used: list[str], story_count: int,
                   days_back: int, audio_format: str | None = None,
                   audio_file: str | None = None) -> dict:
    """Save a report manifest.

    Args:
        report_id: The report identifier (e.g. "2026-04-02-2207")
        articles_used: List of article URL hashes included in the report
        story_count: Number of editorial stories produced
        days_back: How many days of articles were considered
        audio_format: Audio format if audio was generated
        audio_file: Audio filename if audio was generated
    """
    rdir = report_dir(report_id)
    rdir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "id": report_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "days_back": days_back,
        "article_count": len(articles_used),
        "story_count": story_count,
        "articles_used": articles_used,
        "audio_format": audio_format,
        "audio_file": audio_file,
    }

    (rdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def load_manifest(report_id: str) -> dict | None:
    """Load a report manifest."""
    path = report_dir(report_id) / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_reports() -> list[dict]:
    """List all reports, newest first."""
    reports = []
    if not REPORTS_DIR.exists():
        return reports
    for rdir in REPORTS_DIR.iterdir():
        if not rdir.is_dir():
            continue
        manifest_path = rdir / "manifest.json"
        if manifest_path.exists():
            try:
                reports.append(json.loads(manifest_path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
    reports.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return reports


def save_transcript(report_id: str, transcript: str) -> Path:
    """Save a transcript to the report directory."""
    rdir = report_dir(report_id)
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "transcript.txt"
    path.write_text(transcript)
    return path


def save_links(report_id: str, links: str) -> Path:
    """Save a links file to the report directory."""
    rdir = report_dir(report_id)
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / "links.md"
    path.write_text(links)
    return path


def save_audio(report_id: str, audio_data: bytes, audio_format: str) -> Path:
    """Save audio to the report directory."""
    rdir = report_dir(report_id)
    rdir.mkdir(parents=True, exist_ok=True)
    filename = f"weather-report-{report_id}.{audio_format}"
    path = rdir / filename
    path.write_bytes(audio_data)
    return path


def get_audio_duration(report_id: str) -> str | None:
    """Get audio duration using afinfo (macOS). Returns formatted string or None."""
    import subprocess
    manifest = load_manifest(report_id)
    if not manifest or not manifest.get("audio_file"):
        return None
    audio_path = report_dir(report_id) / manifest["audio_file"]
    if not audio_path.exists():
        return None
    try:
        result = subprocess.run(
            ["afinfo", str(audio_path)],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.split("\n"):
            if "estimated duration:" in line.lower():
                secs = float(line.split(":")[-1].strip().split()[0])
                mins = int(secs // 60)
                remaining = int(secs % 60)
                return f"{mins}:{remaining:02d}"
    except Exception:
        pass
    return None
