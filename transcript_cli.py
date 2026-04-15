import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from vtt_cleaner import clean_vtt_text
from youtube_fetch import _subtitle_language, fetch_auto_sub_vtt


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
    parser.add_argument(
        "--allow-non-english",
        action="store_true",
        help="Allow non-English subtitle tracks when English subtitles are unavailable.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON with cleaned transcript text, language, and used_fallback.",
    )
    args = parser.parse_args(argv)

    input_value = args.input
    used_fallback = False
    url_clean_basename: str | None = None

    if _looks_like_url(input_value):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            try:
                fetch_result = fetch_auto_sub_vtt(
                    input_value,
                    tmp_path,
                    allow_non_english=args.allow_non_english,
                )
            except RuntimeError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            vtt_path = fetch_result.path
            language = fetch_result.language
            used_fallback = fetch_result.used_fallback
            try:
                cleaned_text = clean_vtt_text(vtt_path.read_text(encoding="utf-8"))
            except OSError as exc:
                print(f"Error: unable to read {vtt_path}: {exc}", file=sys.stderr)
                return 1
            if not args.json and not args.stdout:
                url_clean_basename = vtt_path.with_suffix(".clean.txt").name
    elif input_value.lower().endswith(".vtt"):
        vtt_path = Path(input_value)
        if not vtt_path.is_file():
            print(f"Error: VTT file not found: {vtt_path}", file=sys.stderr)
            return 1
        language = _subtitle_language(vtt_path)
        try:
            cleaned_text = clean_vtt_text(vtt_path.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"Error: unable to read {vtt_path}: {exc}", file=sys.stderr)
            return 1
    else:
        print("Error: input must be a URL or a .vtt file path.", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {"text": cleaned_text, "language": language, "used_fallback": used_fallback},
                ensure_ascii=False,
            )
        )
        return 0

    if args.stdout:
        print(cleaned_text)
        return 0

    if url_clean_basename is not None:
        output_path = Path.cwd() / url_clean_basename
    else:
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
