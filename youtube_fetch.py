from dataclasses import dataclass
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path


@dataclass(frozen=True)
class SubtitleFetchResult:
    path: Path
    language: str
    used_fallback: bool = False


_SUB_LANGS_ENGLISH_ONLY = "en"
_SUB_LANGS_BROADER = "all"
_SUB_LANG_SKIP_SUFFIXES = frozenset({"orig"})

_MAX_RATE_LIMIT_RETRIES = 1
_INITIAL_RETRY_SLEEP_SECONDS = 1.0
_MAX_RETRY_SLEEP_SECONDS = 30.0
_RATE_LIMIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b429\b"),
    re.compile(r"(?i)too\s+many\s+requests"),
    re.compile(r"(?i)rate[-\s]?limit"),
)

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


def _cache_root_from_env() -> Path | None:
    raw = os.environ.get("YOUTUBE_TRANSCRIPT_CACHE_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _parse_allow_non_english_cache_stem(stem: str, video_id: str) -> tuple[str, bool] | None:
    """Parse ``{video_id}-allow-non-english-...`` filename stem into language and ``used_fallback``."""
    prefix = f"{video_id}-allow-non-english-"
    if not stem.startswith(prefix):
        return None
    body = stem[len(prefix) :]
    if "-" in body:
        lang_part, flag = body.rsplit("-", 1)
        if flag in ("0", "1"):
            return lang_part, flag == "1"
    if body == "en":
        return "en", False
    return body, True


def _try_subtitle_cache_hit(
    cache_root: Path,
    video_id: str,
    allow_non_english: bool,
) -> SubtitleFetchResult | None:
    if not cache_root.is_dir():
        return None
    if not allow_non_english:
        candidate = cache_root / f"{video_id}-en.vtt"
        if candidate.is_file():
            return SubtitleFetchResult(path=candidate, language="en", used_fallback=False)
        return None

    matches: list[Path] = []
    for path in cache_root.glob(f"{video_id}-allow-non-english-*.vtt"):
        parsed = _parse_allow_non_english_cache_stem(path.stem, video_id)
        if parsed is not None:
            matches.append(path)
    if len(matches) != 1:
        return None
    path = matches[0]
    parsed = _parse_allow_non_english_cache_stem(path.stem, video_id)
    if parsed is None:
        return None
    language, used_fallback = parsed
    return SubtitleFetchResult(path=path, language=language, used_fallback=used_fallback)


def _cache_dest_path(
    cache_root: Path,
    video_id: str,
    language: str,
    used_fallback: bool,
    allow_non_english: bool,
) -> Path:
    if not allow_non_english:
        return cache_root / f"{video_id}-en.vtt"
    fb = 1 if used_fallback else 0
    return cache_root / f"{video_id}-allow-non-english-{language}-{fb}.vtt"


def _write_subtitle_cache(
    cache_root: Path,
    video_id: str,
    source: Path,
    language: str,
    used_fallback: bool,
    allow_non_english: bool,
) -> None:
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        dest = _cache_dest_path(cache_root, video_id, language, used_fallback, allow_non_english)
        shutil.copy2(source, dest)
    except OSError:
        return


def _maybe_write_subtitle_cache(
    cache_root: Path | None,
    video_id: str | None,
    source: Path,
    language: str,
    used_fallback: bool,
    allow_non_english: bool,
) -> None:
    if cache_root is None or not video_id:
        return
    _write_subtitle_cache(cache_root, video_id, source, language, used_fallback, allow_non_english)


def _is_rate_limited_error(exc: subprocess.CalledProcessError) -> bool:
    text = f"{exc.stderr or ''}\n{exc.stdout or ''}"
    return any(pattern.search(text) for pattern in _RATE_LIMIT_PATTERNS)


def _retry_sleep_seconds(attempt: int) -> float:
    capped = min(_INITIAL_RETRY_SLEEP_SECONDS * (2**attempt), _MAX_RETRY_SLEEP_SECONDS)
    return float(random.uniform(0.5 * capped, capped))


def _fetch_auto_sub_attempt(
    target_dir: Path,
    url: str,
    sub_langs: str,
) -> tuple[list[Path], subprocess.CalledProcessError | None]:
    """Run yt-dlp auto-subtitle fetch with an explicit ``--sub-langs`` value.

    On HTTP 429-like failures with no new subtitle files, performs a bounded retry
    with backoff. Non-rate-limit errors return immediately. If any run produces
    new ``.vtt`` files, those paths are returned even when yt-dlp exits non-zero.

    Returns fresh ``.vtt`` paths (by mtime vs snapshot) and any
    ``CalledProcessError`` if yt-dlp exited non-zero on the final try (files may
    still be present).
    """
    before_files = {path: path.stat().st_mtime_ns for path in target_dir.glob("*.vtt")}
    command = [
        "yt-dlp",
        *_impersonate_cli_args(),
        "--write-auto-subs",
        "--skip-download",
        "--sub-langs",
        sub_langs,
        "--sub-format",
        "vtt",
        "--output",
        "%(title)s [%(id)s].%(ext)s",
        url,
    ]

    attempt = 0
    while True:
        run_error: subprocess.CalledProcessError | None = None
        try:
            subprocess.run(
                command,
                cwd=target_dir,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("yt-dlp is not installed or is not available on PATH.") from exc
        except subprocess.CalledProcessError as exc:
            run_error = exc

        fresh_files = _fresh_vtt_files(target_dir, before_files)

        if run_error is None:
            return fresh_files, None

        if fresh_files:
            return fresh_files, run_error

        if not _is_rate_limited_error(run_error):
            return fresh_files, run_error

        if attempt >= _MAX_RATE_LIMIT_RETRIES:
            return fresh_files, run_error

        time.sleep(_retry_sleep_seconds(attempt))
        attempt += 1


def _is_likely_orig_track(path: Path) -> bool:
    """True when the filename marks an ``orig`` subtitle variant (not ``-original``, etc.)."""
    name = path.name
    if ".orig." in name:
        return True
    start = 0
    while True:
        idx = name.find("-orig", start)
        if idx == -1:
            return False
        after = idx + len("-orig")
        if after >= len(name) or name[after] in ".-":
            return True
        start = idx + 1


def _is_english_subtitle(path: Path) -> bool:
    """True if any language segment before ``.vtt`` indicates English (``en``, ``en-*``)."""
    for suf in path.suffixes[:-1]:
        tag = suf.lstrip(".").lower().replace("_", "-")
        if tag == "en" or tag.startswith("en-"):
            return True
    return False


def _select_non_english_subtitle(paths: list[Path]) -> Path:
    """Pick one subtitle path using orig preference, then (language code, filename)."""
    orig_candidates = [path for path in paths if _is_likely_orig_track(path)]
    pool = orig_candidates if orig_candidates else paths
    return sorted(pool, key=lambda path: (_subtitle_language(path), path.name))[0]


def fetch_auto_sub_vtt(
    url: str,
    output_dir: Path | str,
    allow_non_english: bool = False,
) -> SubtitleFetchResult:
    target_dir = Path(output_dir)
    cache_root = _cache_root_from_env()
    video_id = _youtube_video_id(url)
    if cache_root is not None and video_id is not None:
        cached = _try_subtitle_cache_hit(cache_root, video_id, allow_non_english)
        if cached is not None:
            return cached

    fresh_files, run_error = _fetch_auto_sub_attempt(
        target_dir,
        url,
        _SUB_LANGS_ENGLISH_ONLY,
    )

    english_files = [path for path in fresh_files if _is_english_subtitle(path)]
    if english_files:
        selected_path = english_files[-1]
        _delete_paths([path for path in fresh_files if path != selected_path])
        _maybe_write_subtitle_cache(
            cache_root,
            video_id,
            selected_path,
            "en",
            False,
            allow_non_english,
        )
        return SubtitleFetchResult(path=selected_path, language="en", used_fallback=False)

    if fresh_files:
        languages = ", ".join(_subtitle_language_list(fresh_files))
    else:
        languages = ""

    _delete_paths(fresh_files)

    if not allow_non_english:
        if languages:
            details = f"English subtitles unavailable; found subtitle languages: {languages}."
            if run_error is not None:
                error_text = run_error.stderr.strip() or run_error.stdout.strip()
                if error_text:
                    details = f"{details} yt-dlp reported: {error_text}"
            raise RuntimeError(details) from run_error

        if run_error is not None:
            details = run_error.stderr.strip() or run_error.stdout.strip() or "yt-dlp failed to download subtitles."
            raise RuntimeError(details) from run_error

        raise RuntimeError("yt-dlp completed but no new .vtt subtitle file was created.")

    fresh_files_broad, run_error_broad = _fetch_auto_sub_attempt(
        target_dir,
        url,
        _SUB_LANGS_BROADER,
    )

    english_files_broad = [path for path in fresh_files_broad if _is_english_subtitle(path)]
    if english_files_broad:
        selected_path = english_files_broad[-1]
        _delete_paths([path for path in fresh_files_broad if path != selected_path])
        _maybe_write_subtitle_cache(
            cache_root,
            video_id,
            selected_path,
            "en",
            True,
            allow_non_english,
        )
        return SubtitleFetchResult(path=selected_path, language="en", used_fallback=True)

    if fresh_files_broad:
        selected_path = _select_non_english_subtitle(fresh_files_broad)
        selected_language = _subtitle_language(selected_path)
        _delete_paths([path for path in fresh_files_broad if path != selected_path])
        _maybe_write_subtitle_cache(
            cache_root,
            video_id,
            selected_path,
            selected_language,
            True,
            allow_non_english,
        )
        return SubtitleFetchResult(path=selected_path, language=selected_language, used_fallback=True)

    if run_error_broad is not None:
        details = run_error_broad.stderr.strip() or run_error_broad.stdout.strip() or "yt-dlp failed to download subtitles."
        raise RuntimeError(details) from run_error_broad

    raise RuntimeError("yt-dlp completed but no new .vtt subtitle file was created.")


def _fresh_vtt_files(target_dir: Path, before_files: dict[Path, int]) -> list[Path]:
    collected: list[tuple[Path, int]] = []
    for path in target_dir.glob("*.vtt"):
        try:
            current_mtime = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue
        previous_mtime = before_files.get(path)
        if previous_mtime is None or current_mtime > previous_mtime:
            collected.append((path, current_mtime))
    collected.sort(key=lambda item: item[1])
    return [path for path, _ in collected]


def _subtitle_language(path: Path) -> str:
    """Language tag from the filename, skipping non-language segments such as ``orig``."""
    suffixes = path.suffixes
    if len(suffixes) < 2:
        return "unknown"
    for suf in reversed(suffixes[:-1]):
        tag = suf.lstrip(".").lower()
        if tag in _SUB_LANG_SKIP_SUFFIXES:
            continue
        return tag or "unknown"
    return "unknown"


def _subtitle_language_list(paths: list[Path]) -> list[str]:
    languages = {_subtitle_language(path) for path in paths}
    return sorted(languages)


def _delete_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            continue
