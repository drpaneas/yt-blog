import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from vtt_cleaner import clean_vtt_text
from youtube_fetch import fetch_auto_sub_vtt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch YouTube auto subtitles or clean an existing VTT transcript.",
    )
    parser.add_argument("input", help="YouTube URL or local .vtt file path")
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the cleaned transcript instead of writing a file.",
    )
    args = parser.parse_args(argv)

    input_value = args.input
    if _looks_like_url(input_value):
        try:
            vtt_path = fetch_auto_sub_vtt(input_value, Path.cwd())
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif input_value.lower().endswith(".vtt"):
        vtt_path = Path(input_value)
        if not vtt_path.is_file():
            print(f"Error: VTT file not found: {vtt_path}", file=sys.stderr)
            return 1
    else:
        print("Error: input must be a URL or a .vtt file path.", file=sys.stderr)
        return 1

    try:
        cleaned_text = clean_vtt_text(vtt_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"Error: unable to read {vtt_path}: {exc}", file=sys.stderr)
        return 1

    if args.stdout:
        print(cleaned_text)
        return 0

    output_path = vtt_path.with_suffix(".clean.txt")
    try:
        output_path.write_text(f"{cleaned_text}\n" if cleaned_text else "", encoding="utf-8")
    except OSError as exc:
        print(f"Error: unable to write {output_path}: {exc}", file=sys.stderr)
        return 1

    print(output_path)
    return 0


def _looks_like_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


if __name__ == "__main__":
    raise SystemExit(main())
