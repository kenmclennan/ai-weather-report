"""Tests for cross-report event dedup.

The same news event covered by a different outlet the next day is a different
URL, so per-article selection cannot catch it. Instead we feed recent reports'
headlines into the editorial prompt so the model skips already-covered events.
"""

from ai_weather_report.reports import parse_report_headlines
from ai_weather_report.pipeline import build_editorial_prompt


# --- parse_report_headlines ---


def test_extracts_headings_from_links_markdown():
    links = (
        "AI Weather Report - Source Links\n\n"
        "Generated: 2026-06-18 12:25\n\n"
        "## GLM-5.2 tops open-weights rankings\n"
        "- [Hugging Face] GLM-5.2\n"
        "  https://example.com/glm\n\n"
        "## Trump administration blocks Anthropic models\n"
        "  https://example.com/anthropic\n"
    )

    assert parse_report_headlines(links) == [
        "GLM-5.2 tops open-weights rankings",
        "Trump administration blocks Anthropic models",
    ]


def test_returns_empty_for_no_headings():
    assert parse_report_headlines("no headings here\njust text\n") == []


def test_returns_empty_for_empty_input():
    assert parse_report_headlines("") == []


# --- build_editorial_prompt ---


def _articles():
    return [
        {"title": "A", "source": "Src", "summary": "summary a"},
        {"title": "B", "source": "Src", "summary": "summary b"},
    ]


def test_prompt_has_no_exclusion_block_without_recent_headlines():
    prompt = build_editorial_prompt(_articles(), days=3, recent_headlines=[])

    assert "already covered" not in prompt.lower()
    assert "summary a" in prompt  # articles still present


def test_prompt_lists_recent_headlines_when_provided():
    headlines = ["GLM-5.2 tops rankings", "Anthropic models blocked"]

    prompt = build_editorial_prompt(_articles(), days=3, recent_headlines=headlines)

    assert "already covered" in prompt.lower()
    for h in headlines:
        assert h in prompt
