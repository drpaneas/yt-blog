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

## Use it

This repo ships a local Claude Code slash command:

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

- run `transcript_cli.py --stdout`
- read `pedagogic.md`
- derive a source-specific outline
- write a Markdown blog post to the repo root

If transcript extraction fails, the command is designed to stop cleanly instead of improvising with unsupported manual fallback steps.

Another way is to no open claude at all, but run it from the command line:

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