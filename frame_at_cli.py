import argparse
import sys
from pathlib import Path

from frame_at import extract_frame_at


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract a single frame from a video at a specific timestamp.",
    )
    parser.add_argument("video_path", type=Path, help="Path to the video file.")
    parser.add_argument("timestamp", type=float, help="Timestamp in seconds (e.g. 42.5).")
    parser.add_argument("output_path", type=Path, help="Output PNG file path.")
    args = parser.parse_args(argv)

    try:
        result = extract_frame_at(args.video_path, args.timestamp, args.output_path)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
