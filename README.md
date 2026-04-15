# Create blogpost from a Youtube video

Fetch YouTube auto-subtitles as clean plaintext, and optionally turn them into blog posts through a local Claude Code command.

Small script repo for two related workflows:

- fetch and clean YouTube auto-subtitles into plain text
- use a local Claude Code slash command to turn a video transcript into a pedagogic blog post

This repo is intentionally a script-based project, not a packaged Python library.

## Requirements

- Python 3.10 or newer
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- Claude Code, to use the `/youtube-blog` slash command.

## Install

Create a virtual environment if you want one, then install the runtime dependency:

```bash
python3 -m pip install -r requirements.txt
```

That installs `yt-dlp`, which the Python scripts invoke via the `yt-dlp` executable on `PATH`.

## Transcript CLI

Fetch subtitles from a YouTube URL and print the cleaned transcript:

```bash
python3 transcript_cli.py "https://www.youtube.com/watch?v=VIDEO_ID" --stdout
```

Clean an existing local `.vtt` file:

```bash
python3 transcript_cli.py "downloaded.en.vtt"
```

Opt into non-English subtitle fallback for URL inputs:

```bash
python3 transcript_cli.py "https://www.youtube.com/watch?v=VIDEO_ID" --stdout --allow-non-english
```

Emit structured JSON for tooling or Claude command workflows:

```bash
python3 transcript_cli.py "https://www.youtube.com/watch?v=VIDEO_ID" --json --allow-non-english
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
- Set **`YOUTUBE_TRANSCRIPT_IMPERSONATE=chrome`** to pass `--impersonate chrome` to `yt-dlp` (TLS fingerprinting; helps some blocked or flaky networks). Install extra support with `python3 -m pip install 'yt-dlp[curl-cffi]'` so impersonation can use curl-cffi.
- Set **`YOUTUBE_TRANSCRIPT_CACHE_DIR=/path/to/cache`** to reuse previously downloaded subtitle files. Cache files are named by video ID and mode (for example `VIDEOID-en.vtt` for English-only runs, or `VIDEOID-allow-non-english-LANG-0|1.vtt` when `--allow-non-english` is used). On a cache hit, the fetcher returns the same `language` and `used_fallback` metadata as a live download.

## Claude Code command

This repo also ships a local Claude Code slash command:

```text
/youtube-blog <youtube-url>
```

To use it:

1. Open Claude Code in this repository.
2. Run:

```text
/youtube-blog https://www.youtube.com/watch?v=VIDEO_ID
```

The command will:

- run `transcript_cli.py` in structured mode
- read `pedagogic.md`
- derive a source-specific outline
- write a Markdown blog post to the repo root

The command still uses `transcript_cli.py` as the only supported ingestion path, but it can opt into non-English subtitle ingestion and still produce the final blog post in English.
If transcript extraction fails, the command is designed to stop cleanly instead of improvising with unsupported manual fallback steps.

Another way is to not open Claude interactively at all, but run it from the command line:

```bash
claude -p "/youtube-blog https://www.youtube.com/watch?v=VIDEO_ID"
```

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

If you want to keep a generated article, move it somewhere intentional before publishing or committing it.