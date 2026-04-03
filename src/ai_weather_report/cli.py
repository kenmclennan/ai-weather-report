"""CLI entry point with subcommands."""

import argparse
import sys

from ai_weather_report import cache, reports
from ai_weather_report.config import (
    get_feeds,
    get_llm_config,
    get_retention_days,
    get_tts_config,
    interactive_setup,
    load_config,
    needs_setup,
    print_config,
)
from ai_weather_report.pipeline import run_fetch, run_report

DEFAULT_DAYS = 3


def cmd_run(args):
    """Full pipeline: fetch, summarise, generate report."""
    config = load_config()
    _ensure_configured(config, args)

    llm_cfg = get_llm_config(config, model=args.llm_model, provider=args.llm_provider)
    tts_cfg = get_tts_config(config, voice=args.voice, speed=args.speed)
    feeds = get_feeds(config, feed_urls=args.feeds)
    retention = get_retention_days(config)

    all_articles = run_fetch(feeds, args.days, args.max_articles, llm_cfg, retention)
    if not all_articles:
        sys.exit(0)

    result = run_report(
        all_articles, args.days, llm_cfg,
        tts_cfg=tts_cfg if not args.text_only else None,
        audio_format=args.format,
        text_only=args.text_only,
    )
    print(f"\nReport: {result['report_id']}")
    if result.get("tts_error"):
        print(f"Warning: TTS failed - {result['tts_error']}", file=sys.stderr)


def cmd_fetch(args):
    """Fetch and summarise only (no report)."""
    config = load_config()
    _ensure_configured(config, args)

    llm_cfg = get_llm_config(config, model=args.llm_model, provider=args.llm_provider)
    feeds = get_feeds(config, feed_urls=args.feeds)
    retention = get_retention_days(config)

    all_articles = run_fetch(feeds, args.days, args.max_articles, llm_cfg, retention)
    print(f"\n{len(all_articles)} articles in cache.")


def cmd_report(args):
    """Generate report from cached articles."""
    config = load_config()
    _ensure_configured(config, args)

    llm_cfg = get_llm_config(config, model=args.llm_model, provider=args.llm_provider)
    tts_cfg = get_tts_config(config, voice=args.voice, speed=args.speed)

    all_articles = cache.load_all_articles()
    all_articles = [a for a in all_articles if a.get("summary")]

    if not all_articles:
        print("No cached articles. Run 'ai-weather-report fetch' first.", file=sys.stderr)
        sys.exit(1)

    print(f"Generating report from {len(all_articles)} cached articles...", file=sys.stderr)
    result = run_report(
        all_articles, args.days, llm_cfg,
        tts_cfg=tts_cfg if not args.text_only else None,
        audio_format=args.format,
        text_only=args.text_only,
    )
    print(f"\nReport: {result['report_id']}")
    if result.get("tts_error"):
        print(f"Warning: TTS failed - {result['tts_error']}", file=sys.stderr)


def cmd_cache_stats(args):
    """Print cache statistics."""
    s = cache.stats()
    print(f"Articles cached: {s['total']}")
    print(f"  In a report:   {s['in_report']}")
    print(f"  Unused:        {s['unused']}")
    if s["oldest"]:
        print(f"  Oldest:        {s['oldest'][:10]}")
    if s["newest"]:
        print(f"  Newest:        {s['newest'][:10]}")

    if s["sources"]:
        print(f"\nBy source:")
        for source, count in s["sources"].items():
            print(f"  {source}: {count}")

    if s["tags"]:
        print(f"\nTop tags:")
        for tag, count in s["tags"].items():
            print(f"  {tag}: {count}")


def cmd_reports_list(args):
    """List generated reports."""
    all_reports = reports.list_reports()
    if not all_reports:
        print("No reports generated yet.")
        return
    print(f"{'ID':<20} {'Stories':>8} {'Articles':>9} {'Audio':<10}")
    print("-" * 50)
    for r in all_reports:
        audio = r.get("audio_file", "")
        if not audio:
            audio = "(text only)"
        print(f"{r['id']:<20} {r['story_count']:>8} {r['article_count']:>9} {audio:<10}")


def cmd_tui(args):
    """Launch the TUI."""
    from ai_weather_report.tui.app import WeatherReportApp
    app = WeatherReportApp()
    app.run()


def cmd_config(args):
    """Print current configuration."""
    print_config()


def cmd_reconfigure(args):
    """Force interactive config setup."""
    config = load_config()
    interactive_setup(config, force=True)


def _ensure_configured(config, args):
    """Run setup if needed."""
    if needs_setup(config):
        interactive_setup(config)
        config = load_config()


def _add_common_args(parser):
    """Add arguments shared across subcommands."""
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help="Days to look back (default: 3)")
    parser.add_argument("--llm-model", help="Override LLM model")
    parser.add_argument("--llm-provider", choices=["anthropic", "openai"],
                        help="Override LLM provider")


def _add_feed_args(parser):
    """Add feed-related arguments."""
    parser.add_argument("--feeds", nargs="+", help="Override feed URLs")
    parser.add_argument("--max-articles", type=int, default=20,
                        help="Max articles per feed (default: 20)")


def _add_output_args(parser):
    """Add output-related arguments."""
    parser.add_argument("--text-only", action="store_true",
                        help="Generate transcript only (no audio)")
    parser.add_argument("--format", choices=["mp3", "wav", "opus", "flac"],
                        default="mp3", help="Audio format (default: mp3)")
    parser.add_argument("--voice", help="Override TTS voice")
    parser.add_argument("--speed", type=float, help="Override TTS speed")


def main():
    parser = argparse.ArgumentParser(
        prog="ai-weather-report",
        description="Generate an AI news audio briefing from RSS feeds.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # run (default)
    p_run = subparsers.add_parser("run", help="Fetch, summarise, and generate report")
    _add_common_args(p_run)
    _add_feed_args(p_run)
    _add_output_args(p_run)
    p_run.set_defaults(func=cmd_run)

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch and summarise only (no report)")
    _add_common_args(p_fetch)
    _add_feed_args(p_fetch)
    p_fetch.set_defaults(func=cmd_fetch)

    # report
    p_report = subparsers.add_parser("report", help="Generate report from cached articles")
    _add_common_args(p_report)
    _add_output_args(p_report)
    p_report.set_defaults(func=cmd_report)

    # tui
    p_tui = subparsers.add_parser("tui", help="Launch interactive TUI")
    p_tui.set_defaults(func=cmd_tui)

    # cache-stats
    p_stats = subparsers.add_parser("cache-stats", help="Show cache statistics")
    p_stats.set_defaults(func=cmd_cache_stats)

    # reports
    p_reports = subparsers.add_parser("reports", help="List generated reports")
    p_reports.set_defaults(func=cmd_reports_list)

    # config
    p_config = subparsers.add_parser("config", help="Show current configuration")
    p_config.set_defaults(func=cmd_config)

    # reconfigure
    p_reconfig = subparsers.add_parser("reconfigure", help="Re-run interactive setup")
    p_reconfig.set_defaults(func=cmd_reconfigure)

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="Manage the background scheduler")
    daemon_sub = p_daemon.add_subparsers(dest="daemon_command")

    p_daemon_run = daemon_sub.add_parser("run", help="Run fetch + optional report now")
    p_daemon_run.set_defaults(func=lambda args: __import__(
        "ai_weather_report.daemon", fromlist=["run_daemon"]).run_daemon())

    p_daemon_install = daemon_sub.add_parser("install", help="Install launchd scheduler")
    p_daemon_install.set_defaults(func=lambda args: __import__(
        "ai_weather_report.daemon", fromlist=["install_daemon"]).install_daemon())

    p_daemon_uninstall = daemon_sub.add_parser("uninstall", help="Remove launchd scheduler")
    p_daemon_uninstall.set_defaults(func=lambda args: __import__(
        "ai_weather_report.daemon", fromlist=["uninstall_daemon"]).uninstall_daemon())

    p_daemon_status = daemon_sub.add_parser("status", help="Show scheduler status")
    p_daemon_status.set_defaults(func=lambda args: __import__(
        "ai_weather_report.daemon", fromlist=["status_daemon"]).status_daemon())

    # Default: show help if just 'daemon' with no subcommand
    p_daemon.set_defaults(func=lambda args: (
        __import__("ai_weather_report.daemon", fromlist=["status_daemon"]).status_daemon()
        if not args.daemon_command else None
    ))

    args = parser.parse_args()

    # Default to 'run' if no subcommand given
    if not args.command:
        # Re-parse with 'run' as default
        args = p_run.parse_args(sys.argv[1:])
        args.func = cmd_run

    args.func(args)
