"""LLM integration - article summarisation and editorial pass."""

import json
import sys

import requests

MAX_ARTICLE_CHARS = 6000

SUMMARY_SYSTEM = (
    "You are a news analyst. Given a full article:\n"
    "1. Write a 2-3 sentence summary capturing the key facts: what happened, "
    "who is involved, and why it matters. Be factual and concise.\n"
    "2. Assign 2-4 short lowercase tags categorising the article's topics "
    "(e.g. models, regulation, funding, robotics, open-source, safety, agents).\n\n"
    "Return ONLY valid JSON: {\"summary\": \"...\", \"tags\": [\"...\", \"...\"]}"
)

EDITORIAL_SYSTEM = (
    "You are the editor of an audio news briefing called The AI Weather Report. "
    "You will receive a list of article summaries with index numbers, titles, and sources.\n\n"
    "Your job:\n"
    "1. Identify the most important and interesting stories.\n"
    "2. Where multiple articles cover the same news, merge them into one story "
    "combining the best information from each source.\n"
    "3. Write a broadcast-style transcript optimised for listening, not reading.\n"
    "4. Each story needs a short spoken headline, the source attribution, and the news.\n\n"
    "Return ONLY valid JSON with this structure:\n"
    '{"stories": [\n'
    '  {"headline": "short spoken headline",\n'
    '   "sources": ["Source Name", ...],\n'
    '   "article_indices": [0, 3, 7],\n'
    '   "body": "The news text written for audio listening. Two to four sentences."}\n'
    "]}\n\n"
    "Guidelines:\n"
    "- Select only the genuinely important developments, not minor updates.\n"
    "- Aim for roughly 8-15 stories depending on how much significant news there is.\n"
    "- The body text should sound natural when read aloud by a text-to-speech voice.\n"
    "- Do not use abbreviations, special characters, or markdown.\n"
    "- Do not start every story with 'In a' or similar repetitive phrasing.\n"
    "- article_indices must reference the index numbers from the input.\n"
    "- Order stories with the most significant news first."
)


def call_llm(text: str, system: str, llm_cfg: dict, max_tokens: int = 4096) -> str:
    """Call the configured LLM provider."""
    provider = llm_cfg["provider"]
    if provider == "anthropic":
        return _call_anthropic(text, system, llm_cfg, max_tokens)
    elif provider == "openai":
        return _call_openai(text, system, llm_cfg, max_tokens)
    else:
        print(f"Error: Unknown LLM provider '{provider}'", file=sys.stderr)
        sys.exit(1)


def _call_anthropic(text, system, llm_cfg, max_tokens):
    import anthropic

    client = anthropic.Anthropic(api_key=llm_cfg["api_key"])
    message = client.messages.create(
        model=llm_cfg["model"],
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": text}],
    )
    return message.content[0].text


def _call_openai(text, system, llm_cfg, max_tokens):
    base_url = llm_cfg.get("api_url", "").strip()
    if not base_url:
        base_url = "https://api.openai.com/v1"
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {llm_cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": llm_cfg["model"],
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
    except requests.RequestException as e:
        print(f"\nError: LLM network error - {e}", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 200:
        print(f"\nError: LLM API returned {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)
    return resp.json()["choices"][0]["message"]["content"]


def summarise_article(title: str, text: str, llm_cfg: dict) -> dict | None:
    """Summarise a single article. Returns {"summary": ..., "tags": [...]} or None."""
    user_text = f'"{title}"\n\n{text[:MAX_ARTICLE_CHARS]}'
    try:
        raw = call_llm(user_text, SUMMARY_SYSTEM, llm_cfg, max_tokens=512)
    except Exception as e:
        print(f"\n  Warning: Failed to summarise '{title}': {e}", file=sys.stderr)
        return None

    # Parse JSON response
    text_clean = raw.strip()
    if text_clean.startswith("```"):
        lines = text_clean.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text_clean = "\n".join(lines)

    try:
        data = json.loads(text_clean)
        return {
            "summary": data.get("summary", ""),
            "tags": data.get("tags", []),
        }
    except json.JSONDecodeError:
        # Fall back to treating the whole response as a summary
        return {"summary": raw.strip(), "tags": []}


def editorial_pass(all_articles: list[dict], days: int, llm_cfg: dict) -> list[dict]:
    """Run the editorial pass to merge, rank, and produce transcript structure."""
    article_list = []
    for i, article in enumerate(all_articles):
        article_list.append(
            f"[{i}] {article['title']}\n"
            f"    Source: {article['source']}\n"
            f"    {article['summary']}"
        )

    user_text = (
        f"Here are {len(all_articles)} AI news articles from the last {days} days.\n"
        f"Select the most important stories, merge duplicate coverage, and produce "
        f"a broadcast transcript.\n\n"
        + "\n\n".join(article_list)
    )

    print("Running editorial pass...", file=sys.stderr)
    raw = call_llm(user_text, EDITORIAL_SYSTEM, llm_cfg, max_tokens=8192)

    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse editorial output as JSON: {e}", file=sys.stderr)
        print("Raw LLM output:", file=sys.stderr)
        print(raw[:500], file=sys.stderr)
        sys.exit(1)

    stories = data.get("stories", [])
    if not stories:
        print("Error: Editorial pass returned no stories.", file=sys.stderr)
        sys.exit(1)

    # Resolve article indices to URLs
    for story in stories:
        story["urls"] = []
        for idx in story.get("article_indices", []):
            if 0 <= idx < len(all_articles):
                story["urls"].append({
                    "title": all_articles[idx]["title"],
                    "url": all_articles[idx]["url"],
                    "source": all_articles[idx]["source"],
                })

    return stories
