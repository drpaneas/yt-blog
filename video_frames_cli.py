import argparse
import json
import logging
import sys
from pathlib import Path

from video_frames import cleanup_video, extract_frames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract key frames from a YouTube video using scene detection, YOLOv8, and OCR.",
    )
    parser.add_argument("url", nargs="?", default=None, help="YouTube video URL")
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write extracted frame PNGs and metadata JSON.",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        default=None,
        help="Use cookies from BROWSER (e.g. chrome) for yt-dlp authentication.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=20,
        help="Maximum number of frames to keep after filtering (default: 20).",
    )
    parser.add_argument(
        "--keep-all",
        action="store_true",
        help="Skip YOLOv8 person filtering, keep all unique scene-change frames.",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Skip OCR step (faster, no text extraction).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print metadata JSON to stdout.",
    )
    parser.add_argument(
        "--cleanup-video",
        type=Path,
        metavar="FRAMES_JSON",
        default=None,
        help="Delete the video file referenced in the given frames.json, then exit.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    if args.cleanup_video:
        ok = cleanup_video(args.cleanup_video)
        return 0 if ok else 1

    if not args.url:
        parser.error("url is required (unless using --cleanup-video)")

    try:
        meta_path = extract_frames(
            url=args.url,
            output_dir=args.output_dir,
            cookies_from_browser=args.cookies_from_browser,
            max_frames=args.max_frames,
            keep_all=args.keep_all,
            skip_ocr=args.no_ocr,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(meta_path.read_text(encoding="utf-8"))
    else:
        print(meta_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
