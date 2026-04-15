from dataclasses import dataclass
import subprocess
from pathlib import Path


@dataclass(frozen=True)
class SubtitleFetchResult:
    path: Path
    language: str
    used_fallback: bool = False


_SUB_LANGS_ENGLISH_ONLY = "en"
_SUB_LANGS_BROADER = "all"
_SUB_LANG_SKIP_SUFFIXES = frozenset({"orig"})


def _fetch_auto_sub_attempt(
    target_dir: Path,
    url: str,
    sub_langs: str,
) -> tuple[list[Path], subprocess.CalledProcessError | None]:
    """Run a single yt-dlp auto-subtitle fetch with an explicit ``--sub-langs`` value.

    Returns fresh ``.vtt`` paths from this attempt (by mtime vs snapshot) and any
    ``CalledProcessError`` if yt-dlp exited non-zero (files may still be present).
    """
    before_files = {path: path.stat().st_mtime_ns for path in target_dir.glob("*.vtt")}
    command = [
        "yt-dlp",
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
    return fresh_files, run_error


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

    fresh_files, run_error = _fetch_auto_sub_attempt(
        target_dir,
        url,
        _SUB_LANGS_ENGLISH_ONLY,
    )

    english_files = [path for path in fresh_files if _is_english_subtitle(path)]
    if english_files:
        selected_path = english_files[-1]
        _delete_paths([path for path in fresh_files if path != selected_path])
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
        return SubtitleFetchResult(path=selected_path, language="en", used_fallback=True)

    if fresh_files_broad:
        selected_path = _select_non_english_subtitle(fresh_files_broad)
        selected_language = _subtitle_language(selected_path)
        _delete_paths([path for path in fresh_files_broad if path != selected_path])
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
