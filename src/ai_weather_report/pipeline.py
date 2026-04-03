"""Pipeline - orchestrates fetch, summarise, editorial, and TTS."""

import re
import sys
from datetime import datetime, timedelta, timezone

from tqdm import tqdm

from ai_weather_report import cache
from ai_weather_report import reports
from ai_weather_report.llm import summarise_article, editorial_pass

CHUNK_SIZE = 1000


# --- Feed fetching ---


def fetch_feeds(feeds_dict: dict, days: int, max_per_feed: int) -> list[dict]:
    """Fetch RSS feeds and return article metadata. Skips cached URLs."""
    import feedparser

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    all_articles = []

    for name, url in feeds_dict.items():
        print(f"  Fetching {name}...", file=sys.stderr, end="", flush=True)
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f" failed ({e})", file=sys.stderr)
            continue

        if feed.bozo and not feed.entries:
            print(f" failed (parse error)", file=sys.stderr)
            continue

        articles = []
        for entry in feed.entries:
            published = None
            for date_field in ("published_parsed", "updated_parsed"):
                parsed = getattr(entry, date_field, None)
                if parsed:
                    published = datetime(*parsed[:6], tzinfo=timezone.utc)
                    break

            if published and published < cutoff:
                continue

            entry_url = entry.get("link", "")
            if not entry_url:
                continue

            articles.append({
                "title": entry.get("title", "Untitled"),
                "url": entry_url,
                "published": published.isoformat() if published else None,
                "source": name,
                "cached": cache.is_cached(entry_url),
            })

        articles.sort(
            key=lambda a: a.get("published") or "",
            reverse=True,
        )
        articles = articles[:max_per_feed]

        feed_new = sum(1 for a in articles if not a["cached"])
        feed_cached = sum(1 for a in articles if a["cached"])
        status_parts = []
        if feed_new:
            status_parts.append(f"{feed_new} new")
        if feed_cached:
            status_parts.append(f"{feed_cached} cached")
        if not status_parts:
            print(f" no recent articles", file=sys.stderr)
        else:
            print(f" {', '.join(status_parts)}", file=sys.stderr)

        all_articles.extend(articles)

    new_count = sum(1 for a in all_articles if not a["cached"])
    cached_count = sum(1 for a in all_articles if a["cached"])
    print(f"\nFound {len(all_articles)} articles ({new_count} new, {cached_count} cached).",
          file=sys.stderr)
    return all_articles


def fetch_article_text(url: str) -> str | None:
    """Download and extract article text."""
    import trafilatura

    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        return trafilatura.extract(downloaded)
    except Exception:
        return None


def fetch_and_summarise(articles: list[dict], llm_cfg: dict,
                        progress_cb=None) -> list[dict]:
    """Fetch full text and summarise new articles. Returns all articles with summaries.

    Cached articles are loaded from the cache. New articles are fetched,
    summarised, and saved to the cache.

    Args:
        progress_cb: Optional callback(stage, current, total, detail) for progress.
                     stage is "fetch" or "summarise".
    """
    result = []
    new_articles = [a for a in articles if not a["cached"]]
    cached_articles = [a for a in articles if a["cached"]]

    # Load cached articles
    for article in cached_articles:
        cached = cache.load_article(article["url"])
        if cached and cached.get("summary"):
            result.append(cached)

    if not new_articles:
        print("All articles already cached.", file=sys.stderr)
        return result

    # Fetch and summarise new articles
    total_new = len(new_articles)
    print(f"\nFetching {total_new} new articles...", file=sys.stderr)
    fetched = 0
    failed = 0

    for i, article in enumerate(tqdm(new_articles, desc="Fetching articles", file=sys.stderr)):
        if progress_cb:
            progress_cb("fetch", i, total_new, article.get("title", ""))
        text = fetch_article_text(article["url"])
        if text:
            article["text"] = text
            fetched += 1
        else:
            failed += 1

    print(f"Extracted {fetched} of {total_new} ({failed} failed).", file=sys.stderr)

    # Filter to those with text
    to_summarise = [a for a in new_articles if a.get("text")]
    total_summarise = len(to_summarise)

    print(f"Summarising {total_summarise} new articles...", file=sys.stderr)
    for i, article in enumerate(tqdm(to_summarise, desc="Summarising", file=sys.stderr)):
        if progress_cb:
            progress_cb("summarise", i, total_summarise, article.get("title", ""))
        llm_result = summarise_article(article["title"], article["text"], llm_cfg)
        if not llm_result:
            continue

        cached_entry = {
            "url": article["url"],
            "title": article["title"],
            "source": article["source"],
            "published": article["published"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "summary": llm_result["summary"],
            "tags": llm_result["tags"],
            "reports": [],
        }
        cache.save_article(cached_entry)
        result.append(cached_entry)

    if progress_cb:
        progress_cb("done", total_summarise, total_summarise, "")

    return result


# --- Output generation ---


def _fix_tts_capitalisation(text: str) -> str:
    """Fix common capitalisation issues for TTS pronunciation."""
    import re

    # Word-boundary replacements for abbreviations and proper nouns
    fixes = {
        r"\bai\b": "AI",
        r"\bapi\b": "API",
        r"\bapis\b": "APIs",
        r"\bgpu\b": "GPU",
        r"\bgpus\b": "GPUs",
        r"\bllm\b": "LLM",
        r"\bllms\b": "LLMs",
        r"\bceo\b": "CEO",
        r"\bcto\b": "CTO",
        r"\beu\b": "EU",
        r"\bopenai\b": "OpenAI",
        r"\bdeepseek\b": "DeepSeek",
        r"\bdeepmind\b": "DeepMind",
        r"\bchatgpt\b": "ChatGPT",
        r"\bgpt\b": "GPT",
        r"\bmeta\b": "Meta",
    }

    for pattern, replacement in fixes.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def build_transcript(stories: list[dict], days: int) -> str:
    """Build the spoken transcript from editorial stories."""
    today = datetime.now().strftime("%B %d, %Y")
    lines = [f"The AI Weather Report for {today}.\n"]

    for story in stories:
        sources = " and ".join(story["sources"]) if story["sources"] else "multiple sources"
        lines.append(f'{story["headline"]}.')
        lines.append(f"From {sources}.")
        lines.append(f'{story["body"]}\n')

    lines.append(f"That's The AI Weather Report for {today}. Stay informed.")
    transcript = "\n".join(lines)
    return _fix_tts_capitalisation(transcript)


def build_links(stories: list[dict]) -> str:
    """Build the links file listing sources for each story."""
    lines = [f"AI Weather Report - Source Links\n"]
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    for story in stories:
        lines.append(f"## {story['headline']}\n")
        for ref in story.get("urls", []):
            lines.append(f"- [{ref['source']}] {ref['title']}")
            lines.append(f"  {ref['url']}")
        lines.append("")

    return "\n".join(lines)


# --- TTS ---


def split_into_chunks(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    """Split text into TTS-friendly chunks."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence
    if current.strip():
        chunks.append(current.strip())
    return chunks


def synthesise_chunks(chunks: list[str], tts_cfg: dict, audio_format: str,
                      progress_cb=None) -> list[bytes]:
    """Generate audio chunks via TTS API."""
    import requests

    url = f"{tts_cfg['api_url'].rstrip('/')}/audio/speech"
    headers = {
        "Authorization": f"Bearer {tts_cfg['api_key']}",
        "Content-Type": "application/json",
    }

    total = len(chunks)
    audio_parts = []
    for i, chunk in enumerate(tqdm(chunks, desc="Generating audio", file=sys.stderr)):
        if progress_cb:
            progress_cb("audio", i, total, f"Generating audio {i + 1}/{total}")
        payload = {
            "model": tts_cfg["model"],
            "input": chunk,
            "voice": tts_cfg["voice"],
            "response_format": audio_format,
            "speed": float(tts_cfg["speed"]),
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
        except requests.RequestException as e:
            print(f"\nError: TTS network error - {e}", file=sys.stderr)
            sys.exit(1)

        if resp.status_code != 200:
            print(f"\nError: TTS API returned {resp.status_code}", file=sys.stderr)
            print(resp.text, file=sys.stderr)
            sys.exit(1)

        audio_parts.append(resp.content)

    return audio_parts


# --- Full pipeline ---


def run_fetch(feeds: dict, days: int, max_per_feed: int, llm_cfg: dict,
              retention_days: int) -> list[dict]:
    """Fetch feeds, summarise new articles, prune cache. Returns all articles."""
    print(f"\nFetching feeds (last {days} days)...", file=sys.stderr)
    articles = fetch_feeds(feeds, days, max_per_feed)

    if not articles:
        print(f"No articles found in the last {days} days.", file=sys.stderr)
        return []

    all_articles = fetch_and_summarise(articles, llm_cfg)

    # Prune old cache entries
    pruned = cache.prune(retention_days)
    if pruned:
        print(f"Pruned {pruned} old articles from cache.", file=sys.stderr)

    print(f"\n{len(all_articles)} articles ready ({sum(1 for a in articles if a['cached'])} from cache).",
          file=sys.stderr)
    return all_articles


def run_report(all_articles: list[dict], days: int, llm_cfg: dict,
               tts_cfg: dict | None = None, audio_format: str = "mp3",
               text_only: bool = False, progress_cb=None) -> str:
    """Generate a report from articles. Returns the report ID.

    Args:
        progress_cb: Optional callback(stage, current, total, detail) for progress.
                     Stages: "editorial", "audio", "done".
    """
    if not all_articles:
        print("No articles to generate a report from.", file=sys.stderr)
        sys.exit(1)

    # Editorial pass
    if progress_cb:
        progress_cb("editorial", 0, 1, "Running editorial pass...")
    stories = editorial_pass(all_articles, days, llm_cfg)
    print(f"Editorial selected {len(stories)} stories.\n", file=sys.stderr)

    # Build outputs
    transcript = build_transcript(stories, days)
    links = build_links(stories)

    # Create report
    report_id = datetime.now().strftime("%Y-%m-%d-%H%M")

    # Save transcript and links
    transcript_path = reports.save_transcript(report_id, transcript)
    links_path = reports.save_links(report_id, links)
    print(f"Transcript: {transcript_path}", file=sys.stderr)
    print(f"Links:      {links_path}", file=sys.stderr)

    # Collect article hashes used in this report
    used_urls = set()
    for story in stories:
        for idx in story.get("article_indices", []):
            if 0 <= idx < len(all_articles):
                used_urls.add(all_articles[idx]["url"])

    # Mark articles as used in this report
    used_hashes = []
    for url in used_urls:
        cache.mark_in_report(url, report_id)
        used_hashes.append(cache.url_hash(url))

    audio_file = None
    if not text_only and tts_cfg:
        chunks = split_into_chunks(transcript)
        print(f"Split into {len(chunks)} audio chunks.", file=sys.stderr)

        audio_parts = synthesise_chunks(chunks, tts_cfg, audio_format,
                                        progress_cb=progress_cb)
        audio_data = b"".join(audio_parts)
        audio_path = reports.save_audio(report_id, audio_data, audio_format)
        audio_file = audio_path.name

        size_mb = len(audio_data) / (1024 * 1024)
        print(f"Audio:      {audio_path} ({size_mb:.1f}MB)", file=sys.stderr)

    # Save manifest
    reports.save_manifest(
        report_id=report_id,
        articles_used=used_hashes,
        story_count=len(stories),
        days_back=days,
        audio_format=audio_format if not text_only else None,
        audio_file=audio_file,
    )

    if progress_cb:
        progress_cb("done", 1, 1, "")

    report_dir = reports.report_dir(report_id)
    print(f"\nOutput in {report_dir}/", file=sys.stderr)
    return report_id
