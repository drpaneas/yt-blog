import logging
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 600


def _audio_extension(audio_url: str) -> str:
    parsed_path = urllib.parse.urlparse(audio_url).path
    suffix = Path(parsed_path).suffix.lower()
    if suffix in (".mp3", ".m4a", ".ogg", ".wav", ".flac", ".opus"):
        return suffix
    return ".mp3"


def download_audio(
    audio_url: str, dest_dir: Path, episode_id: str
) -> Path | None:
    parsed = urllib.parse.urlparse(audio_url)
    if parsed.scheme not in ("http", "https"):
        logger.error("Refusing to download non-HTTP URL: %s", audio_url)
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = _audio_extension(audio_url)
    dest_path = dest_dir / f"podcast-{episode_id}{ext}"
    if dest_path.exists() and dest_path.stat().st_size > 0:
        logger.info("Audio already downloaded: %s", dest_path.name)
        return dest_path
    logger.info("Downloading audio: %s", audio_url)
    fd, tmp_path = tempfile.mkstemp(
        dir=dest_dir, suffix=ext, prefix=f"podcast-{episode_id}-"
    )
    try:
        os.close(fd)
        req = urllib.request.Request(
            audio_url,
            headers={"User-Agent": "youtube-blog-automation/1.0"},
        )
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
        Path(tmp_path).replace(dest_path)
    except OSError as exc:
        logger.error("Failed to download audio: %s", exc)
        Path(tmp_path).unlink(missing_ok=True)
        return None
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise
    logger.info("Downloaded: %s (%.1f MB)", dest_path.name,
                dest_path.stat().st_size / (1024 * 1024))
    return dest_path


def load_whisper_model(model_name: str = "large-v3"):
    try:
        import whisper
    except ImportError:
        logger.error(
            "openai-whisper is not installed. "
            "Run: pip install openai-whisper"
        )
        return None
    logger.info("Loading Whisper model '%s'...", model_name)
    try:
        return whisper.load_model(model_name)
    except Exception as exc:
        logger.error("Failed to load Whisper model: %s", exc)
        return None


def transcribe_audio(audio_path: Path, model) -> dict | None:
    if model is None:
        logger.error("No Whisper model provided")
        return None
    logger.info("Transcribing %s...", audio_path.name)
    try:
        result = model.transcribe(str(audio_path))
    except Exception as exc:
        logger.error("Transcription failed: %s", exc)
        return None
    text = result.get("text", "").strip()
    language = result.get("language", "unknown")
    if not text:
        logger.error("Transcription produced empty text")
        return None
    logger.info(
        "Transcription complete: %d characters, language=%s",
        len(text), language,
    )
    return {"text": text, "language": language}
