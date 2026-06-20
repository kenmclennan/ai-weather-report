# Cross-report event dedup

## Problem

Per-article report selection (`select_report_articles`) stops the *same article*
from recurring across reports, but the same news *event* covered by a different
outlet the next day is a different URL. It is summarised, unreported, and so it
is eligible again - the editorial pass merges duplicate coverage within a single
run but has no memory of what previous reports already covered. Result: stories
like "GLM-5.2 tops open-weights rankings" recur for several days under slightly
different headlines.

## Approach

LLM-prompt exclusion. Feed the headlines of recent reports into the editorial
prompt and instruct the model to skip stories that are substantially the same,
unless there is a genuinely new development. This fits the existing LLM-centric
design, needs no new infrastructure, and relies on the model's semantic
judgement (the same judgement it already uses to merge within-run duplicates).

## Lookback window

Headlines come from reports created within the last `fetch_days` days - the same
window an article can linger in the cache. If an article is still fetch-eligible,
the reports that already covered its event fall in that same window. No new
config value.

## Source of headlines

Parse the `## <headline>` lines from each recent report's existing `links.md`.
These files already exist for every past report, so this works retroactively
with no migration.

## Units

Pure (unit-tested):

- `reports.parse_report_headlines(links_md_text) -> list[str]` - extract the
  `## ` headings from a links.md body.
- `pipeline.build_editorial_prompt(articles, days, recent_headlines) -> str` -
  extracted from `editorial_pass`. Builds the user prompt; when
  `recent_headlines` is non-empty, appends an "already covered recently - only
  repeat if genuinely new" block listing each headline.

Thin IO glue (not unit-tested):

- `reports.recent_report_headlines(within_days) -> list[str]` - read recent
  reports' `links.md` files, parse, de-duplicate, return.
- `pipeline.editorial_pass(..., recent_headlines=None)` - optional param,
  defaults to `None` (backward compatible); passes through to
  `build_editorial_prompt`.
- `run_report` gathers headlines via `reports.recent_report_headlines` and
  passes them to `editorial_pass`.

## Behaviour

The editorial LLM keeps doing within-run merging unchanged. The new block tells
it which events are already on the air. A genuinely new development on a covered
topic is still allowed through - the instruction is "only repeat if there is a
new development", not a hard ban.

## Tests

- `parse_report_headlines`: extracts headings, ignores non-heading lines,
  handles empty input.
- `build_editorial_prompt`: no recent headlines -> no exclusion block; with
  headlines -> block present and lists each headline.
