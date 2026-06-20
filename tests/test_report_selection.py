"""Tests for selecting which articles are eligible for a new report.

Regression cover for the duplicate-stories bug: the CLI report paths fed every
in-window article into the editorial pass without excluding ones already
included in a previous report, so the same stories recurred report after report.
"""

from ai_weather_report.pipeline import select_report_articles


def test_excludes_articles_already_in_a_report():
    articles = [
        {"url": "a", "summary": "s", "reports": ["2026-06-18-1225"]},
        {"url": "b", "summary": "s", "reports": []},
    ]

    selected = select_report_articles(articles)

    assert [a["url"] for a in selected] == ["b"]


def test_excludes_articles_without_a_summary():
    articles = [
        {"url": "a", "summary": "", "reports": []},
        {"url": "b", "reports": []},
        {"url": "c", "summary": "s", "reports": []},
    ]

    selected = select_report_articles(articles)

    assert [a["url"] for a in selected] == ["c"]


def test_returns_empty_when_everything_already_reported():
    articles = [
        {"url": "a", "summary": "s", "reports": ["2026-06-18-1225"]},
        {"url": "b", "summary": "s", "reports": ["2026-06-17-1249"]},
    ]

    assert select_report_articles(articles) == []


def test_missing_reports_key_is_treated_as_unreported():
    articles = [
        {"url": "a", "summary": "s"},
    ]

    selected = select_report_articles(articles)

    assert [a["url"] for a in selected] == ["a"]
