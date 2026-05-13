"""Video frame extraction pipeline.

Downloads a YouTube video, detects scene changes, deduplicates frames,
filters out people-only frames with YOLOv8, and runs OCR on the rest.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_YOUTUBE_VIDEO_ID_RE = re.compile(
    r"(?:[?&]v=|/shorts/|/embed/|/live/|youtu\.be/)([0-9A-Za-z_-]{11})(?:[?&#/]|$)",
)


def _youtube_video_id(url: str) -> str | None:
    match = _YOUTUBE_VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def _impersonate_cli_args() -> list[str]:
    value = os.environ.get("YOUTUBE_TRANSCRIPT_IMPERSONATE", "").strip()
    if not value:
        return []
    return ["--impersonate", value]


def _cookies_cli_args(cookies_from_browser: str | None = None) -> list[str]:
    value = cookies_from_browser or os.environ.get("YOUTUBE_TRANSCRIPT_COOKIES_BROWSER", "").strip()
    if not value:
        return []
    return ["--cookies-from-browser", value]


# ---------------------------------------------------------------------------
# Stage 1: Download video
# ---------------------------------------------------------------------------

def download_video(
    url: str,
    output_dir: Path,
    cookies_from_browser: str | None = None,
) -> Path:
    """Download a YouTube video at 480p or lower. Returns path to the file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / "%(id)s.%(ext)s")

    command = [
        "yt-dlp",
        *_impersonate_cli_args(),
        *_cookies_cli_args(cookies_from_browser),
        "-f", "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "--merge-output-format", "mp4",
        "-o", output_template,
        url,
    ]

    logger.info("Downloading video: %s", url)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("yt-dlp is not installed or not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip() or "yt-dlp failed"
        raise RuntimeError(f"Video download failed: {details}") from exc

    video_files = list(output_dir.glob("*.mp4"))
    if not video_files:
        all_files = list(output_dir.iterdir())
        if all_files:
            return all_files[0]
        raise RuntimeError("yt-dlp completed but no video file was created.")

    return max(video_files, key=lambda p: p.stat().st_mtime)


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return 0.0


# ---------------------------------------------------------------------------
# Stage 2: Scene detection + dedup
# ---------------------------------------------------------------------------

def detect_scenes(video_path: Path, output_dir: Path) -> list[tuple[Path, float]]:
    """Detect scene changes and save frames. Returns [(path, timestamp_sec), ...]."""
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector

    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=12.0))
    scene_manager.detect_scenes(video)

    scene_list = scene_manager.get_scene_list()
    if not scene_list:
        logger.warning("No scene changes detected")
        return []

    import cv2
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames: list[tuple[Path, float]] = []
    prev_ts_int = -1
    sub_seq = 0

    for scene_start, _ in scene_list:
        timestamp_sec = scene_start.get_seconds()
        frame_number = int(timestamp_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        if not ret:
            continue

        ts_int = int(timestamp_sec)
        if ts_int == prev_ts_int:
            sub_seq += 1
        else:
            sub_seq = 0
            prev_ts_int = ts_int

        if sub_seq == 0:
            filename = f"frame-{ts_int:04d}s.png"
        else:
            filename = f"frame-{ts_int:04d}s-{sub_seq}.png"
        frame_path = output_dir / filename
        cv2.imwrite(str(frame_path), frame)
        frames.append((frame_path, timestamp_sec))

    cap.release()
    logger.info("Extracted %d scene-change frames", len(frames))
    return frames


def _dhash(image, hash_size: int = 8) -> int:
    """Compute difference hash of an image (OpenCV BGR array)."""
    import cv2
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (hash_size + 1, hash_size))
    diff = resized[:, 1:] > resized[:, :-1]
    result = 0
    for val in diff.flatten():
        result = (result << 1) | int(val)
    return result


def _hamming_distance(h1: int, h2: int) -> int:
    return bin(h1 ^ h2).count("1")


def deduplicate_frames(
    frames: list[tuple[Path, float]],
    threshold: int = 6,
) -> list[tuple[Path, float]]:
    """Remove near-identical consecutive frames using perceptual hashing."""
    if not frames:
        return []

    import cv2
    kept: list[tuple[Path, float]] = []
    prev_hash: int | None = None

    for path, ts in frames:
        img = cv2.imread(str(path))
        if img is None:
            continue
        current_hash = _dhash(img)
        if prev_hash is not None and _hamming_distance(prev_hash, current_hash) < threshold:
            path.unlink(missing_ok=True)
            continue
        kept.append((path, ts))
        prev_hash = current_hash

    removed = len(frames) - len(kept)
    if removed:
        logger.info("Dedup removed %d near-identical frames, %d remaining", removed, len(kept))
    return kept


# ---------------------------------------------------------------------------
# Stage 3: YOLOv8 person filtering
# ---------------------------------------------------------------------------

def filter_persons(
    frames: list[tuple[Path, float]],
    confidence_threshold: float = 0.5,
    person_area_ratio: float = 0.15,
) -> list[tuple[Path, float, str]]:
    """Filter out frames dominated by people. Returns [(path, ts, tag), ...]."""
    from ultralytics import YOLO
    from ultralytics import settings as ul_settings
    import cv2

    raw_weights = ul_settings.get("weights_dir", "")
    weights_path = Path(raw_weights).expanduser() if raw_weights else None
    if weights_path is None or not weights_path.is_absolute():
        weights_path = Path.home() / ".cache" / "ultralytics"
    weights_path.mkdir(parents=True, exist_ok=True)
    model_path = weights_path / "yolov8n.pt"
    model = YOLO(str(model_path))
    PERSON_CLASS = 0
    SCREEN_CLASSES = {62, 63, 67, 73}  # tv, laptop, cell phone, book

    kept: list[tuple[Path, float, str]] = []

    for path, ts in frames:
        img = cv2.imread(str(path))
        if img is None:
            continue

        results = model(img, verbose=False)
        h, w = img.shape[:2]
        total_area = h * w

        person_area = 0.0
        has_screen = False

        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if conf < confidence_threshold:
                continue

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            box_area = (x2 - x1) * (y2 - y1)

            if cls_id == PERSON_CLASS:
                person_area += box_area
            elif cls_id in SCREEN_CLASSES:
                has_screen = True

        person_ratio = person_area / total_area

        if person_ratio > person_area_ratio and not has_screen:
            logger.debug("Discarding frame %s (person ratio %.2f)", path.name, person_ratio)
            path.unlink(missing_ok=True)
            continue

        if has_screen:
            tag = "screen"
        elif person_ratio > 0.05:
            tag = "mixed"
        else:
            tag = "fullscreen"

        kept.append((path, ts, tag))

    removed = len(frames) - len(kept)
    if removed:
        logger.info("YOLOv8 filtered out %d person-dominated frames, %d remaining", removed, len(kept))
    return kept


# ---------------------------------------------------------------------------
# Stage 4: OCR + content classification
# ---------------------------------------------------------------------------

_CODE_SYNTAX = re.compile(
    r"[{}\[\]();]|->|=>|::|&&|\|\||[!=]==|<<|>>|#include|#define|@import|:\s*$",
    re.MULTILINE,
)

_CODE_KEYWORDS = re.compile(
    r"\b(?:def|fn|func|function|class|struct|enum|impl|import|return|"
    r"const|let|var|while|match|switch|case|catch|pub|"
    r"void|int|bool|char|float|string|println|printf|std)\b"
)


def _classify_ocr_text(text: str) -> str:
    """Classify OCR text as 'code', 'slide', or 'diagram'."""
    if not text or len(text.strip()) < 10:
        return "diagram"

    lines = text.strip().split("\n")
    syntax_matches = len(_CODE_SYNTAX.findall(text))
    keyword_matches = len(_CODE_KEYWORDS.findall(text))
    total_indicators = syntax_matches + keyword_matches

    if syntax_matches >= 3 and total_indicators > 4:
        return "code"
    if total_indicators / max(len(lines), 1) > 1.0:
        return "code"

    return "slide"


def run_ocr(
    frames: list[tuple[Path, float, str]],
) -> list[dict]:
    """Run EasyOCR on frames and classify content. Returns frame metadata dicts."""
    import easyocr

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    results: list[dict] = []

    for path, ts, tag in frames:
        try:
            ocr_results = reader.readtext(str(path), detail=0, paragraph=True)
            ocr_text = "\n".join(ocr_results).strip() if ocr_results else None
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("OCR failed for %s: %s", path.name, exc, exc_info=True)
            ocr_text = None

        content_type = _classify_ocr_text(ocr_text) if ocr_text else "diagram"

        results.append({
            "file": path.name,
            "timestamp_sec": round(ts, 1),
            "type": content_type,
            "ocr_text": ocr_text,
        })

    logger.info(
        "OCR classified %d frames: %d code, %d slide, %d diagram",
        len(results),
        sum(1 for r in results if r["type"] == "code"),
        sum(1 for r in results if r["type"] == "slide"),
        sum(1 for r in results if r["type"] == "diagram"),
    )
    return results


# ---------------------------------------------------------------------------
# Stage 5: Metadata + cleanup
# ---------------------------------------------------------------------------

def write_metadata(
    output_dir: Path,
    video_id: str | None,
    duration_sec: float,
    frame_data: list[dict],
) -> Path:
    """Write frames metadata JSON. Returns path to the JSON file."""
    metadata = {
        "video_id": video_id,
        "total_duration_sec": round(duration_sec, 1),
        "frame_count": len(frame_data),
        "frames": frame_data,
    }
    meta_path = output_dir / "frames.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote metadata to %s (%d frames)", meta_path, len(frame_data))
    return meta_path


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def extract_frames(
    url: str,
    output_dir: Path,
    cookies_from_browser: str | None = None,
    max_frames: int = 20,
    keep_all: bool = False,
    skip_ocr: bool = False,
) -> Path:
    """Run the full frame extraction pipeline. Returns path to metadata JSON."""
    import tempfile

    video_id = _youtube_video_id(url)
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        video_path = download_video(url, tmp_path, cookies_from_browser)
        duration = get_video_duration(video_path)

        frames = detect_scenes(video_path, output_dir)
        frames = deduplicate_frames(frames)

    if not keep_all:
        tagged_frames = filter_persons(frames)
    else:
        tagged_frames = [(p, ts, "fullscreen") for p, ts in frames]

    if len(tagged_frames) > max_frames:
        for path, _, _ in tagged_frames[max_frames:]:
            path.unlink(missing_ok=True)
        tagged_frames = tagged_frames[:max_frames]
        logger.info("Capped to %d frames", max_frames)

    if skip_ocr:
        frame_data = [
            {"file": p.name, "timestamp_sec": round(ts, 1), "type": "unknown", "ocr_text": None}
            for p, ts, _ in tagged_frames
        ]
    else:
        frame_data = run_ocr(tagged_frames)

    return write_metadata(output_dir, video_id, duration, frame_data)
