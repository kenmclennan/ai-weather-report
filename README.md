# AI Weather Report

Generate an AI news audio briefing from RSS feeds.

Fetches recent AI news, summarises articles with an LLM, runs an editorial pass to merge duplicates and rank importance, then produces a broadcast-style transcript and optional TTS audio. Articles are cached locally so repeated runs only summarise new content.

## How it works

1. **Fetch** - Pulls recent articles from configurable RSS feeds
2. **Extract** - Downloads and extracts full article text (skips cached articles)
3. **Summarise** - LLM compresses each article to 2-3 sentences with free-form tags
4. **Cache** - Stores summaries in `~/.ai-weather-report/cache/` for reuse
5. **Editorial** - LLM merges duplicate coverage, ranks by importance, produces broadcast transcript
6. **Audio** - TTS API converts transcript to spoken audio (optional)

## Install

```bash
# With uv
uv pip install -e .

# Or with pip
pip install -e .
```

## Usage

```bash
# Full pipeline: fetch, summarise, generate report (default)
ai-weather-report
ai-weather-report run

# Fetch and summarise only (no report)
ai-weather-report fetch

# Generate report from cached articles
ai-weather-report report

# Text-only (no audio)
ai-weather-report run --text-only

# Custom options
ai-weather-report run --days 1 --format opus

# Cache statistics
ai-weather-report cache-stats

# List generated reports
ai-weather-report reports

# Show current config
ai-weather-report config

# Reconfigure
ai-weather-report reconfigure
```

## Configuration

Config and data are stored in `~/.ai-weather-report/`:

```
~/.ai-weather-report/
  config.ini              # API keys, feeds, settings
  cache/articles/         # Cached article summaries (JSON)
  reports/                # Generated reports with audio
```

Config sections:
- **[tts]** - TTS API URL, key, voice, speed, model
- **[llm]** - Provider (anthropic/openai), model, API key, optional API URL
- **[general]** - Cache retention days (default: 30)
- **[feeds]** - RSS feed name/URL pairs

Default feeds cover Ars Technica, The Verge, TechCrunch, Wired, VentureBeat, MIT Technology Review, OpenAI, Google DeepMind, and Hugging Face.

## Output

Reports are saved to `~/.ai-weather-report/reports/{id}/`:

- `manifest.json` - Report metadata and article references
- `transcript.txt` - The spoken transcript
- `links.md` - Source links for each story
- `weather-report.mp3` - Audio file (unless `--text-only`)

## License

MIT
