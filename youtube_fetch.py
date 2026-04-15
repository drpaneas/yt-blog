import subprocess
from pathlib import Path


def fetch_auto_sub_vtt(url: str, output_dir: Path | str) -> Path:
    target_dir = Path(output_dir)
    before_files = {path: path.stat().st_mtime_ns for path in target_dir.glob("*.vtt")}
    command = [
        "yt-dlp",
        "--write-auto-subs",
        "--skip-download",
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
    english_files = [path for path in fresh_files if _subtitle_language(path) == "en"]
    if english_files:
        _delete_paths([path for path in fresh_files if path not in english_files])
        return english_files[-1]

    if fresh_files:
        languages = ", ".join(_subtitle_language_list(fresh_files))
        _delete_paths(fresh_files)
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


def _fresh_vtt_files(target_dir: Path, before_files: dict[Path, int]) -> list[Path]:
    fresh_files: list[Path] = []
    for path in target_dir.glob("*.vtt"):
        previous_mtime = before_files.get(path)
        current_mtime = path.stat().st_mtime_ns
        if previous_mtime is None or current_mtime > previous_mtime:
            fresh_files.append(path)
    return sorted(fresh_files, key=lambda path: path.stat().st_mtime_ns)


def _subtitle_language(path: Path) -> str:
    suffixes = path.suffixes
    if len(suffixes) >= 2:
        return suffixes[-2].lstrip(".").lower() or "unknown"
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
