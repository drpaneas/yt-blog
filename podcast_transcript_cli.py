import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from podcast_fetch import fetch_episodes, fetch_podcast_info
from podcast_transcript import download_audio, load_whisper_model, transcribe_audio


def _extract_podcast_id(url_or_id: str) -> tuple[str, str | None]:
    """Extract podcast ID and optional episode ID from a PodcastIndex URL or raw ID."""
    import re
    from urllib.parse import urlparse, parse_qs

    if url_or_id.isdigit():
        return url_or_id, None

    match = re.search(r"podcastindex\.org/podcast/(\d+)", url_or_id)
    if not match:
        raise ValueError(
            f"Unsupported URL format: {url_or_id}\n"
            "Only PodcastIndex URLs are supported. Examples:\n"
            "  https://podcastindex.org/podcast/6958769\n"
            "  https://podcastindex.org/podcast/6958769?episode=53451816130\n"
            "  6958769  (raw podcast ID)\n"
            "Find your podcast at https://podcastindex.org and use that URL."
        )
    podcast_id = match.group(1)
    parsed = urlparse(url_or_id)
    episode_param = parse_qs(parsed.query).get("episode", [None])[0]
    return podcast_id, episode_param


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and transcribe a podcast episode from PodcastIndex.",
    )
    parser.add_argument("input", help="PodcastIndex URL or podcast ID")
    parser.add_argument(
        "--json", action="store_true",
        help="Print machine-readable JSON with transcript text and language.",
    )
    parser.add_argument(
        "--whisper-model", default="large-v3",
        help="Whisper model to use (default: large-v3)",
    )
    args = parser.parse_args(argv)

    try:
        podcast_id, episode_param = _extract_podcast_id(args.input)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    podcast_info = fetch_podcast_info(podcast_id)
    if not podcast_info:
        print(f"Error: Could not fetch podcast info for ID {podcast_id}", file=sys.stderr)
        return 1

    episodes = fetch_episodes(podcast_id)
    if not episodes:
        print(f"Error: No episodes found for podcast {podcast_id}", file=sys.stderr)
        return 1

    if episode_param:
        matching = [e for e in episodes if e["episode_id"] == episode_param]
        if not matching:
            print(f"Error: Episode {episode_param} not found", file=sys.stderr)
            return 1
        episode = matching[0]
    else:
        episode = episodes[0]

    print(f"Episode: {episode['title']}", file=sys.stderr)
    print("Downloading audio...", file=sys.stderr)

    audio_dir = Path(tempfile.mkdtemp(prefix="podcast-audio-"))
    try:
        audio_path = download_audio(episode["audio_url"], audio_dir, episode["episode_id"])
        if audio_path is None:
            print("Error: Audio download failed", file=sys.stderr)
            return 1

        print(f"Transcribing with {args.whisper_model}...", file=sys.stderr)
        model = load_whisper_model(args.whisper_model)
        if model is None:
            print("Error: Could not load Whisper model", file=sys.stderr)
            return 1

        result = transcribe_audio(audio_path, model)
        if result is None:
            print("Error: Transcription failed", file=sys.stderr)
            return 1
    finally:
        shutil.rmtree(audio_dir, ignore_errors=True)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["text"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
