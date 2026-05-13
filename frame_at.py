"""Extract a single frame from a video file at a specific timestamp using ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_frame_at(video_path: Path, timestamp_sec: float, output_path: Path) -> Path:
    """Extract one frame from video_path at timestamp_sec, write to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-ss", str(timestamp_sec),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        "-y",
        str(output_path),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is not installed or not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or "ffmpeg failed"
        raise RuntimeError(f"Frame extraction failed: {details}") from exc

    if not output_path.exists():
        raise RuntimeError(f"ffmpeg completed but {output_path} was not created.")

    return output_path
