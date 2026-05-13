# Auto-publish blog posts from YouTube and podcasts

Turn YouTube videos and podcast episodes into pedagogic blog posts using Claude Code, and optionally sync them to an LLM wiki.

Script repo for four workflows:

- fetch and clean YouTube auto-subtitles into plain text
- extract key video frames (code, diagrams, slides) using YOLOv8 + OCR
- use Claude Code slash commands to turn video or podcast transcripts into blog posts, optionally enriched with extracted video frames
- automated blog publishing from YouTube channels and podcast feeds, with optional LLM wiki integration

![Hugo blog with auto-published posts](assets/hugo-blog-screenshot.png)

![LLM wiki knowledge graph](assets/llmwiki-graph-screenshot.png)

The project can be used as loose scripts or installed as a Python package with CLI entry points (see [Install](#install)).

## Requirements

- Python 3.10 or newer
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/) (for video frame extraction)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code), to use the slash commands and autopublish scripts
- [openai-whisper](https://github.com/openai/whisper) (for podcast transcription only)

## Install

### Option A: pip install (recommended)

Install as an editable package into a virtual environment. This creates CLI commands (`transcript-cli`, `autopublish`, etc.) that work from any directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

To make the commands available system-wide without activating the venv, symlink them into a directory on your `PATH`:

```bash
ln -sf "$(pwd)/.venv/bin/transcript-cli" /opt/homebrew/bin/transcript-cli
ln -sf "$(pwd)/.venv/bin/autopublish" /opt/homebrew/bin/autopublish
ln -sf "$(pwd)/.venv/bin/podcast-transcript-cli" /opt/homebrew/bin/podcast-transcript-cli
ln -sf "$(pwd)/.venv/bin/podcast-autopublish" /opt/homebrew/bin/podcast-autopublish
ln -sf "$(pwd)/.venv/bin/video-frames" /opt/homebrew/bin/video-frames
ln -sf "$(pwd)/.venv/bin/frame-at" /opt/homebrew/bin/frame-at
```

### Option B: requirements.txt only

If you prefer running the scripts directly with `python3 script.py`, just install the dependencies:

```bash
python3 -m pip install -r requirements.txt
```

This installs `yt-dlp` (invoked via the `yt-dlp` executable on `PATH`) and `openai-whisper` (used for podcast audio transcription).

### yt-dlp impersonation support

To avoid YouTube 429 rate limits, install `curl_cffi` into the Python environment that yt-dlp uses. If yt-dlp was installed via Homebrew, that's its own isolated environment:

```bash
$(dirname $(realpath $(which yt-dlp)))/../libexec/bin/python -m pip install 'curl_cffi>=0.10,<0.15'
```

Verify with `yt-dlp --list-impersonate-targets` - targets should show as available, not `(unavailable)`.

### Installed CLI commands

When installed as a package, these commands are available:

| Command | Description |
|---------|-------------|
| `transcript-cli` | Fetch and clean YouTube subtitles |
| `podcast-transcript-cli` | Fetch and transcribe podcast episodes |
| `video-frames` | Extract key frames from YouTube videos (YOLOv8 + OCR) |
| `frame-at` | Extract a single frame at a specific timestamp from a video file |
| `autopublish` | YouTube blog generation and publishing pipeline |
| `podcast-autopublish` | Podcast blog generation and publishing pipeline |

## Configuration

Copy the example config and fill in your details:

```bash
cp channels.toml.example channels.toml
```

`channels.toml` is gitignored so your personal config stays local. It contains:

- `[paths]` - paths to your Hugo blog repo, this repo, and optionally an LLM wiki directory
- `[hugo]` - Hugo front matter categories and tags for YouTube posts
- `[podcast_hugo]` - Hugo front matter categories and tags for podcast posts
- `[[channel]]` entries - YouTube channels to poll via RSS
- `[[podcast]]` entries - PodcastIndex podcast IDs to poll
- `max_parallel` - max concurrent Claude instances for blog generation
- `max_episodes_per_podcast` - how many recent episodes to fetch per podcast
- `state_dir` - custom state directory for tracking processed items (default: `~/.youtube-blog-automation/`)

### Multiple pipelines

You can run independent pipelines from the same codebase by using separate config files with different `state_dir` values:

```bash
autopublish --config ~/astronomy/channels.toml
autopublish --config ~/retro-gaming/channels.toml
podcast-autopublish --config ~/trips/channels.toml
```

Each config can point to a different blog repo, LLM wiki, and set of channels/podcasts. Set a unique `state_dir` per config so processed items are tracked independently.

### Environment variables

For podcast functionality, set PodcastIndex API credentials:

```bash
export PODCASTINDEX_API_KEY="your-key"
export PODCASTINDEX_API_SECRET="your-secret"
```

Get API credentials at [podcastindex.org/developers](https://podcastindex.org/developers).

Optional YouTube variables:

- `YOUTUBE_TRANSCRIPT_IMPERSONATE=chrome` - pass `--impersonate chrome` to `yt-dlp` (helps with rate limits)
- `YOUTUBE_TRANSCRIPT_COOKIES_BROWSER=chrome` - pass `--cookies-from-browser chrome` to `yt-dlp` (authenticates with your browser session to avoid 429 rate limits)
- `YOUTUBE_TRANSCRIPT_CACHE_DIR=/path/to/cache` - reuse previously downloaded subtitle files

## Transcript CLI

If installed as a package, use `transcript-cli`. Otherwise use `python3 transcript_cli.py`.

Fetch subtitles from a YouTube URL and print the cleaned transcript:

```bash
transcript-cli "https://www.youtube.com/watch?v=VIDEO_ID" --stdout
```

With browser cookie authentication (recommended to avoid 429 rate limits):

```bash
transcript-cli "https://www.youtube.com/watch?v=VIDEO_ID" --stdout --cookies-from-browser chrome
```

Clean an existing local `.vtt` file:

```bash
transcript-cli "downloaded.en.vtt"
```

Opt into non-English subtitle fallback for URL inputs:

```bash
transcript-cli "https://www.youtube.com/watch?v=VIDEO_ID" --stdout --allow-non-english
```

Emit structured JSON for tooling or Claude command workflows:

```bash
transcript-cli "https://www.youtube.com/watch?v=VIDEO_ID" --json --allow-non-english
```

### Language handling

- Default URL ingestion is English-first.
- The fetcher first tries an English-only subtitle pass.
- If `yt-dlp` partially succeeds and still writes a fresh English `.vtt`, the pipeline uses it.
- If only non-English subtitles are available, the plain CLI fails clearly by default instead of silently switching languages.
- Passing `--allow-non-english` lets the CLI retry with a broader subtitle fetch and fall back to a deterministic non-English subtitle track.
- URL subtitle fetches happen in a temporary working directory, so subtitle artifacts are not left in the repo root.
- The `--json` mode is mainly intended for tooling and the Claude command workflow, and currently emits `text`, `language`, and `used_fallback`.

### 429 handling, impersonation, and subtitle cache

- Subtitle fetches use **bounded retry with backoff** when `yt-dlp` fails with HTTP 429-style rate limit signals and no usable new `.vtt` files were written yet.
- Set **`YOUTUBE_TRANSCRIPT_IMPERSONATE=chrome`** to pass `--impersonate chrome` to `yt-dlp` (TLS fingerprinting; helps some blocked or flaky networks). Requires `curl_cffi` installed in yt-dlp's Python environment (see [Install](#yt-dlp-impersonation-support)).
- Pass **`--cookies-from-browser chrome`** (or set **`YOUTUBE_TRANSCRIPT_COOKIES_BROWSER=chrome`**) to authenticate yt-dlp with your browser session. This is the most reliable way to avoid YouTube 429 rate limits.
- Set **`YOUTUBE_TRANSCRIPT_CACHE_DIR=/path/to/cache`** to reuse previously downloaded subtitle files. Cache files are named by video ID and mode (for example `VIDEOID-en.vtt` for English-only runs, or `VIDEOID-allow-non-english-LANG-0|1.vtt` when `--allow-non-english` is used). On a cache hit, the fetcher returns the same `language` and `used_fallback` metadata as a live download.

## Video Frames CLI

Extract key frames from YouTube videos using scene detection, YOLOv8 person filtering, and EasyOCR text extraction. Frames are classified as `code`, `slide`, or `diagram`.

```bash
video-frames "https://www.youtube.com/watch?v=VIDEO_ID" --output-dir ./frames
video-frames "https://www.youtube.com/watch?v=VIDEO_ID" --output-dir ./frames --cookies-from-browser chrome
video-frames "https://www.youtube.com/watch?v=VIDEO_ID" --output-dir ./frames --max-frames 30
```

Options:

- `--output-dir` (required) - directory for frame PNGs and `frames.json` metadata
- `--cookies-from-browser BROWSER` - authenticate yt-dlp with browser cookies
- `--max-frames INT` - cap on frames to keep after filtering (default 20)
- `--keep-all` - skip YOLOv8 person filtering, keep all unique scene-change frames
- `--no-ocr` - skip OCR step (faster, no text extraction)
- `--json` - print metadata JSON to stdout

The pipeline:

1. Downloads the video at best available quality via yt-dlp
2. Detects scene changes with [PySceneDetect](https://github.com/Breakthrough/PySceneDetect)
3. Deduplicates near-identical frames with perceptual hashing
4. Filters out person-dominated frames with [YOLOv8](https://github.com/ultralytics/ultralytics)
5. Extracts text and classifies content with [EasyOCR](https://github.com/JaidedAI/EasyOCR)
6. Writes frame PNGs and a `frames.json` metadata file with timestamps, types, and OCR text

## Claude Code commands

This repo ships three Claude Code slash commands for blog generation.

### YouTube (transcript only)

```text
/youtube-blog <youtube-url>
```

Fetches the transcript, reads `pedagogic.md` for style, derives an outline, and writes a Markdown blog post to the repo root.

### YouTube with video frames

```text
/youtube-eyes <youtube-url>
```

Same pedagogic style as `/youtube-blog`, but also extracts video frames (code screenshots, diagrams, slides) and reconstructs their content in the article. Outputs a Hugo page bundle (directory with `index.md` + any remaining images) instead of a flat `.md` file. Code frames are transcribed into fenced code blocks, diagrams are reconstructed as ASCII art or Markdown, and slides are converted to text. Screenshots are only embedded when the visual is too complex to reproduce faithfully in text.

Falls back to transcript-only mode if frame extraction fails (video unavailable, ffmpeg missing, etc.).

### Podcast

```text
/podcast-blog <podcastindex-url>
```

Fetches and transcribes the podcast episode using Whisper, then generates a blog post. Accepts PodcastIndex URLs like `https://podcastindex.org/podcast/123456?episode=789`.

All commands can be run non-interactively from the terminal. You must run from the `~/youtube` directory (or use `-d`) since the commands are defined in `.claude/commands/`:

```bash
cd ~/youtube && claude -p "/youtube-blog https://www.youtube.com/watch?v=VIDEO_ID"
cd ~/youtube && claude -p "/youtube-eyes https://www.youtube.com/watch?v=VIDEO_ID"
cd ~/youtube && claude -p "/podcast-blog https://podcastindex.org/podcast/123456"
```

With browser cookie authentication:

```bash
cd ~/youtube && YOUTUBE_TRANSCRIPT_COOKIES_BROWSER=chrome claude -p "/youtube-eyes https://www.youtube.com/watch?v=VIDEO_ID"
```

Or point at the project from any directory using `-d`:

```bash
YOUTUBE_TRANSCRIPT_COOKIES_BROWSER=chrome claude -p "/youtube-eyes https://www.youtube.com/watch?v=VIDEO_ID" -d ~/youtube
```

## Autopublish

Automated scripts that poll RSS feeds, generate blog posts, and publish them to a Hugo blog repo.

### YouTube autopublish

```bash
autopublish              # poll RSS feeds, generate and publish new posts
autopublish --dry-run    # show what would be processed
autopublish --url "https://www.youtube.com/watch?v=VIDEO_ID"  # process single video
autopublish --url "..." --force  # reprocess even if already seen
autopublish --url "..." --cookies-from-browser chrome  # with browser cookie auth
autopublish --url "..." --use-eyes --cookies-from-browser chrome  # with video frame extraction
autopublish --use-eyes  # batch mode with video frames for all new videos
```

### Podcast autopublish

```bash
podcast-autopublish                # poll PodcastIndex, transcribe, generate, publish
podcast-autopublish --dry-run      # show what would be processed
podcast-autopublish --url "https://podcastindex.org/podcast/123456?episode=789"
podcast-autopublish --url "..." --force          # reprocess
podcast-autopublish --url "..." --generate-only  # generate markdown without publishing
podcast-autopublish --whisper-model base          # use smaller Whisper model
```

Both scripts:

- Track processed episodes in `~/.youtube-blog-automation/` to avoid reprocessing
- Run Claude in headless mode to generate blog posts
- Add Hugo front matter with AI-generated tags
- Commit to the configured blog repo
- Optionally copy to an LLM wiki directory

## Tests

Run the full test suite with:

```bash
python3 -m unittest discover -s tests
```

## Generated outputs

Downloaded subtitle files, cleaned transcript files, and generated blog posts are local working artifacts and are ignored by git:

- `*.vtt`
- `*.clean.txt`
- `youtube-blog-*.md`
- `youtube-blog-*/` (page bundles from `/youtube-eyes`)
- `podcast-blog-*.md`
- `frames/` (standalone frame extraction output)

If you want to keep a generated article, move it somewhere intentional before publishing or committing it.
