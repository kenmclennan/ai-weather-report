"""Daemon - scheduled feed fetching and report generation."""

import io
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ai_weather_report import cache, reports
from ai_weather_report.config import (
    DATA_DIR, get_auto_report, get_feeds, get_fetch_days, get_llm_config,
    get_notify, get_retention_days, get_schedule_time, get_tts_config,
    load_config,
)
from ai_weather_report.pipeline import fetch_and_summarise, fetch_feeds, run_report

PLIST_NAME = "com.ai-weather-report.daemon"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_NAME}.plist"
LOG_DIR = DATA_DIR / "logs"


def notify(title: str, message: str) -> None:
    """Send a macOS notification."""
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def run_daemon() -> None:
    """Run the daemon: fetch feeds, summarise, optionally generate report."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"daemon-{datetime.now().strftime('%Y-%m-%d-%H%M')}.log"

    # Redirect output to log file
    log_file = open(log_path, "w")
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = log_file
    sys.stderr = log_file

    try:
        _run_daemon_inner()
    except Exception as e:
        print(f"Daemon error: {e}", file=log_file)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        log_file.close()

    # Prune old log files (keep last 30)
    logs = sorted(LOG_DIR.glob("daemon-*.log"), reverse=True)
    for old_log in logs[30:]:
        old_log.unlink(missing_ok=True)


def _run_daemon_inner() -> None:
    """Inner daemon logic."""
    config = load_config()
    llm_cfg = get_llm_config(config)
    feeds = get_feeds(config)
    retention = get_retention_days(config)
    fetch_days = get_fetch_days(config)
    auto_report = get_auto_report(config)
    should_notify = get_notify(config)

    print(f"Daemon run at {datetime.now().isoformat()}")
    print(f"Feeds: {len(feeds)}, fetch_days: {fetch_days}, auto_report: {auto_report}")

    # Step 1: Fetch and summarise
    articles = fetch_feeds(feeds, days=fetch_days, max_per_feed=20)
    if not articles:
        print("No articles found.")
        if should_notify:
            notify("AI Weather Report", "No new articles found.")
        return

    all_articles = fetch_and_summarise(articles, llm_cfg)
    cache.prune(retention)

    new_count = sum(1 for a in articles if not a.get("cached"))
    print(f"Fetched {len(all_articles)} articles ({new_count} new).")

    if not auto_report:
        if should_notify:
            notify("AI Weather Report", f"Feed updated: {new_count} new articles.")
        return

    # Step 2: Generate report from unreported articles
    unreported = [a for a in all_articles if a.get("summary") and not a.get("reports")]
    if not unreported:
        print("No unreported articles for report.")
        if should_notify:
            notify("AI Weather Report", f"Feed updated: {new_count} new articles. No new stories for report.")
        return

    # Calculate days since last report
    last_reports = reports.list_reports()
    if last_reports:
        last_created = last_reports[0].get("created_at", "")
        try:
            last_dt = datetime.fromisoformat(last_created)
            days_since = (datetime.now(timezone.utc) - last_dt).days or 1
        except (ValueError, TypeError):
            days_since = fetch_days
    else:
        days_since = fetch_days

    tts_cfg = get_tts_config(config)

    result = run_report(
        unreported, days=days_since, llm_cfg=llm_cfg,
        tts_cfg=tts_cfg, audio_format="mp3",
    )

    report_id = result["report_id"]
    tts_error = result.get("tts_error")

    if tts_error:
        print(f"Report {report_id} generated (TTS failed: {tts_error})")
        if should_notify:
            notify("AI Weather Report",
                   f"Report ready (no audio - TTS unavailable). {len(unreported)} articles.")
    else:
        print(f"Report {report_id} generated with audio.")
        if should_notify:
            notify("AI Weather Report",
                   f"New report ready with audio. {len(unreported)} articles.")


def generate_plist() -> str:
    """Generate the launchd plist XML."""
    import shutil
    exe = shutil.which("ai-weather-report")
    if not exe:
        print("Error: ai-weather-report not found on PATH", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    schedule_time = get_schedule_time(config)
    try:
        hour, minute = schedule_time.split(":")
        hour, minute = int(hour), int(minute)
    except (ValueError, AttributeError):
        hour, minute = 6, 0

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
        <string>daemon</string>
        <string>run</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{LOG_DIR}/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/launchd-stderr.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def install_daemon() -> None:
    """Install the launchd plist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    plist = generate_plist()
    PLIST_PATH.write_text(plist)

    # Unload first if already loaded
    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
    )

    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        config = load_config()
        schedule_time = get_schedule_time(config)
        print(f"Daemon installed. Scheduled daily at {schedule_time}.")
        print(f"Plist: {PLIST_PATH}")
        print(f"Logs:  {LOG_DIR}/")
        print(f"\nTo run immediately: ai-weather-report daemon run")
        print(f"To uninstall: ai-weather-report daemon uninstall")
    else:
        print(f"Error installing daemon: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def uninstall_daemon() -> None:
    """Uninstall the launchd plist."""
    if not PLIST_PATH.exists():
        print("Daemon not installed.")
        return

    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
    )
    PLIST_PATH.unlink(missing_ok=True)
    print("Daemon uninstalled.")


def status_daemon() -> None:
    """Show daemon status."""
    config = load_config()
    schedule_time = get_schedule_time(config)
    auto_report = get_auto_report(config)

    print(f"Schedule time:  {schedule_time}")
    print(f"Auto report:    {auto_report}")
    print(f"Plist path:     {PLIST_PATH}")
    print(f"Installed:      {PLIST_PATH.exists()}")

    if PLIST_PATH.exists():
        result = subprocess.run(
            ["launchctl", "list", PLIST_NAME],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"Status:         loaded")
        else:
            print(f"Status:         not loaded")

    # Show last log
    if LOG_DIR.exists():
        logs = sorted(LOG_DIR.glob("daemon-*.log"), reverse=True)
        if logs:
            print(f"\nLast run log:   {logs[0]}")
            print(logs[0].read_text()[:500])
