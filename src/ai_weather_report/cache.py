"""Article cache - filesystem-backed store for summarised articles."""

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_weather_report.config import CACHE_DIR


def url_hash(url: str) -> str:
    """Generate a short hash from a URL for use as a filename."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def article_path(url: str) -> Path:
    """Get the cache file path for an article URL."""
    return CACHE_DIR / f"{url_hash(url)}.json"


def is_cached(url: str) -> bool:
    """Check if an article URL is already in the cache."""
    return article_path(url).exists()


def load_article(url: str) -> dict | None:
    """Load a cached article by URL. Returns None if not cached."""
    path = article_path(url)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_all_articles() -> list[dict]:
    """Load all cached articles."""
    articles = []
    if not CACHE_DIR.exists():
        return articles
    for path in CACHE_DIR.glob("*.json"):
        try:
            articles.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    articles.sort(
        key=lambda a: a.get("published", "") or "",
        reverse=True,
    )
    return articles


def save_article(article: dict) -> None:
    """Save an article to the cache.

    Expected fields: url, title, source, published, fetched_at, summary, tags, reports
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = article_path(article["url"])
    article["url_hash"] = url_hash(article["url"])
    path.write_text(json.dumps(article, indent=2, default=str))


def mark_in_report(url: str, report_id: str) -> None:
    """Mark an article as used in a report."""
    article = load_article(url)
    if article is None:
        return
    reports = article.get("reports", [])
    if report_id not in reports:
        reports.append(report_id)
        article["reports"] = reports
        save_article(article)


def prune(retention_days: int) -> int:
    """Remove articles older than retention_days. Returns count removed."""
    if not CACHE_DIR.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for path in CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            path.unlink(missing_ok=True)
            removed += 1
            continue
        fetched = data.get("fetched_at", "")
        if not fetched:
            continue
        try:
            fetched_dt = datetime.fromisoformat(fetched)
        except ValueError:
            continue
        if fetched_dt < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def stats() -> dict:
    """Return cache statistics."""
    articles = load_all_articles()
    total = len(articles)
    in_report = sum(1 for a in articles if a.get("reports"))
    unused = total - in_report

    sources = Counter(a.get("source", "unknown") for a in articles)
    tags = Counter()
    for a in articles:
        for tag in a.get("tags", []):
            tags[tag] += 1

    oldest = None
    newest = None
    for a in articles:
        pub = a.get("published", "")
        if pub:
            if oldest is None or pub < oldest:
                oldest = pub
            if newest is None or pub > newest:
                newest = pub

    return {
        "total": total,
        "in_report": in_report,
        "unused": unused,
        "sources": dict(sources.most_common()),
        "tags": dict(tags.most_common(20)),
        "oldest": oldest,
        "newest": newest,
    }
