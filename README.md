# AI Weather Report

Generate an AI news audio briefing from RSS feeds.

Fetches recent AI news, summarizes articles with an LLM, runs an editorial pass to merge duplicates and rank importance, then produces a broadcast-style transcript and optional TTS audio.

## How it works

1. **Fetch** - Pulls recent articles from configurable RSS feeds
2. **Extract** - Downloads and extracts full article text
3. **Summarize** - LLM compresses each article to 2-3 sentences
4. **Editorial** - LLM merges duplicate coverage, ranks by importance, produces broadcast transcript
5. **Audio** - TTS API converts transcript to spoken audio (optional)

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (dependencies are managed inline via PEP 723)
- An Anthropic or OpenAI-compatible API key for summarization
- An OpenAI-compatible TTS API for audio generation (optional)

## Usage

```bash
# First run - interactive setup for API keys and feeds
./ai-weather-report

# Text-only (no audio)
./ai-weather-report --text-only

# Custom options
./ai-weather-report --days 1 --format opus --output-dir ./today

# Show current config
./ai-weather-report --config

# Reconfigure
./ai-weather-report --reconfigure
```

## Configuration

Config is stored at `~/.ai-weather-report` in INI format with three sections:

- **[tts]** - TTS API URL, key, voice, speed, model
- **[llm]** - Provider (anthropic/openai), model, API key, optional API URL
- **[feeds]** - RSS feed name/URL pairs

Default feeds cover Ars Technica, The Verge, TechCrunch, Wired, VentureBeat, MIT Technology Review, OpenAI, Google DeepMind, and Hugging Face.

## Output

Each run creates a timestamped directory containing:

- `transcript.txt` - The spoken transcript
- `links.md` - Source links for each story
- `weather-report.mp3` - Audio file (unless `--text-only`)

## License

MIT
