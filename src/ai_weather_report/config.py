"""Configuration management with migration from flat file to directory."""

import configparser
import shutil
import sys
from pathlib import Path

DATA_DIR = Path.home() / ".ai-weather-report"
CONFIG_PATH = DATA_DIR / "config.ini"
CACHE_DIR = DATA_DIR / "cache" / "articles"
REPORTS_DIR = DATA_DIR / "reports"

# Legacy flat config path (pre-0.2)
LEGACY_CONFIG_PATH = Path.home() / ".ai-weather-report"

DEFAULT_FEEDS = {
    # News outlets
    "Ars Technica AI": "https://arstechnica.com/ai/feed/",
    "The Verge AI": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "TechCrunch AI": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "Wired AI": "https://www.wired.com/feed/tag/ai/latest/rss",
    "VentureBeat AI": "https://venturebeat.com/category/ai/feed/",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
    # AI company blogs
    "OpenAI": "https://openai.com/news/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    # Dev tools & engineering
    "Simon Willison": "https://simonwillison.net/atom/everything/",
    "The Pragmatic Engineer": "https://newsletter.pragmaticengineer.com/feed",
    "GitHub AI & ML": "https://github.blog/ai-and-ml/feed/",
    # AI research (accessible)
    "Import AI": "https://importai.substack.com/feed",
    "Ahead of AI": "https://magazine.sebastianraschka.com/feed",
    "The Gradient": "https://thegradientpub.substack.com/feed",
    # Enterprise adoption
    "Sequoia Capital": "https://www.sequoiacap.com/feed/",
    "a16z": "https://www.a16z.news/feed",
    # AI coding & architecture
    "The Phoenix Architecture": "https://aicoding.leaflet.pub/rss",
    "Martin Fowler": "https://martinfowler.com/feed.atom",
}

TTS_DEFAULTS = {
    "api_url": "https://tts.clu.ninja/v1",
    "api_key": "",
    "voice": "af_bella(2)+af_nicole(7)",
    "speed": "1.1",
    "model": "kokoro",
}

LLM_DEFAULTS = {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key": "",
    "api_url": "",
}

GENERAL_DEFAULTS = {
    "retention_days": "30",
}

TTS_REQUIRED = ("api_url", "api_key", "voice")


def ensure_dirs():
    """Create the data directory structure if it doesn't exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_config():
    """Migrate flat ~/.ai-weather-report file to directory structure.

    If ~/.ai-weather-report exists as a regular file (old format),
    move it to ~/.ai-weather-report/config.ini inside the new directory.
    """
    legacy = LEGACY_CONFIG_PATH

    # Already a directory - nothing to migrate
    if legacy.is_dir():
        return

    # No legacy config exists
    if not legacy.exists():
        ensure_dirs()
        return

    # It's a file - migrate it
    print(f"Migrating config from {legacy} to {DATA_DIR}/config.ini...", file=sys.stderr)
    content = legacy.read_text()
    legacy.unlink()
    ensure_dirs()
    CONFIG_PATH.write_text(content)
    print("Config migrated successfully.", file=sys.stderr)


def load_config():
    """Load config, migrating from legacy format if needed."""
    migrate_legacy_config()
    ensure_dirs()
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case in keys (esp. feed names)
    config.read(CONFIG_PATH)
    return config


def save_config(config):
    """Save config to the data directory."""
    ensure_dirs()
    with open(CONFIG_PATH, "w") as f:
        config.write(f)


def needs_setup(config):
    """Check if required config values are missing."""
    for key in TTS_REQUIRED:
        if not config.get("tts", key, fallback="").strip():
            return True
    if not config.get("llm", "api_key", fallback="").strip():
        return True
    return False


def interactive_setup(config, force=False):
    """Run interactive configuration setup."""
    print("ai-weather-report config setup", file=sys.stderr)
    print("-" * 31, file=sys.stderr)

    # TTS section
    if not config.has_section("tts"):
        config.add_section("tts")
    print("\n--- TTS settings ---", file=sys.stderr)
    for key, default in TTS_DEFAULTS.items():
        existing = config.get("tts", key, fallback="").strip()
        if existing and not force:
            continue
        display_default = existing if existing else default
        prompt = f"{key.replace('_', ' ').title()} [{display_default}]: "
        value = input(prompt).strip()
        if not value:
            value = display_default
        config.set("tts", key, value)

    # LLM section
    if not config.has_section("llm"):
        config.add_section("llm")
    print("\n--- LLM settings (required) ---", file=sys.stderr)
    for key, default in LLM_DEFAULTS.items():
        existing = config.get("llm", key, fallback="").strip()
        if existing and not force:
            continue
        display_default = existing if existing else default
        hint = ""
        if key == "provider":
            hint = " (anthropic or openai)"
        elif key == "api_url":
            hint = " (leave blank for default)"
        prompt = f"{key.replace('_', ' ').title()}{hint} [{display_default}]: "
        value = input(prompt).strip()
        if not value:
            value = display_default
        config.set("llm", key, value)

    # General section
    if not config.has_section("general"):
        config.add_section("general")
    if force or not config.get("general", "retention_days", fallback="").strip():
        existing = config.get("general", "retention_days", fallback="").strip()
        display_default = existing if existing else GENERAL_DEFAULTS["retention_days"]
        value = input(f"Cache retention days [{display_default}]: ").strip()
        if not value:
            value = display_default
        config.set("general", "retention_days", value)

    # Feeds section
    if not config.has_section("feeds"):
        config.add_section("feeds")
        for name, url in DEFAULT_FEEDS.items():
            config.set("feeds", name, url)
        print("\nDefault RSS feeds added. Edit config to customize.", file=sys.stderr)
    elif force:
        print("\nFeeds unchanged. Edit config to add/remove feeds.", file=sys.stderr)

    save_config(config)
    print(f"\nConfig saved to {CONFIG_PATH}\n", file=sys.stderr)


def get_tts_config(config, voice=None, speed=None):
    """Extract TTS config with optional overrides."""
    result = {}
    for key, default in TTS_DEFAULTS.items():
        result[key] = config.get("tts", key, fallback=default)
    if voice:
        result["voice"] = voice
    if speed is not None:
        result["speed"] = str(speed)
    return result


def get_llm_config(config, model=None, provider=None):
    """Extract LLM config with optional overrides."""
    cfg = {}
    for key, default in LLM_DEFAULTS.items():
        cfg[key] = config.get("llm", key, fallback=default)
    if not cfg["api_key"].strip():
        print("Error: LLM must be configured. Run: ai-weather-report reconfigure", file=sys.stderr)
        sys.exit(1)
    if model:
        cfg["model"] = model
    if provider:
        cfg["provider"] = provider
    return cfg


def get_feeds(config, feed_urls=None):
    """Get feeds dict, with optional URL overrides."""
    if feed_urls:
        from urllib.parse import urlparse
        feeds = {}
        for url in feed_urls:
            name = urlparse(url).netloc.replace("www.", "")
            feeds[name] = url
        return feeds
    if config.has_section("feeds") and config.options("feeds"):
        return dict(config.items("feeds"))
    return dict(DEFAULT_FEEDS)


def get_retention_days(config):
    """Get cache retention period in days."""
    return int(config.get("general", "retention_days",
                          fallback=GENERAL_DEFAULTS["retention_days"]))


def print_config():
    """Print current configuration."""
    config = load_config()
    print(f"Config file: {CONFIG_PATH}\n")

    print("[TTS]")
    if not config.has_section("tts"):
        print("  Not configured.")
    else:
        for key in TTS_DEFAULTS:
            val = config.get("tts", key, fallback="(not set)")
            if key == "api_key" and val and val != "(not set)":
                val = val[:4] + "..." + val[-4:] if len(val) > 8 else "****"
            print(f"  {key}: {val}")

    print("\n[LLM]")
    if not config.has_section("llm"):
        print("  Not configured.")
    else:
        for key in LLM_DEFAULTS:
            val = config.get("llm", key, fallback="(not set)")
            if key == "api_key" and val and val != "(not set)":
                val = val[:4] + "..." + val[-4:] if len(val) > 8 else "****"
            if key == "api_url" and not val.strip():
                val = "(default for provider)"
            print(f"  {key}: {val}")

    print("\n[General]")
    print(f"  retention_days: {config.get('general', 'retention_days', fallback=GENERAL_DEFAULTS['retention_days'])}")

    print(f"\n[Data]")
    print(f"  data_dir: {DATA_DIR}")
    print(f"  cache_dir: {CACHE_DIR}")
    print(f"  reports_dir: {REPORTS_DIR}")

    print("\n[Feeds]")
    if not config.has_section("feeds") or not config.options("feeds"):
        print("  Using defaults.")
    else:
        for name, url in config.items("feeds"):
            print(f"  {name}: {url}")
