import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
from io import BytesIO

from podcast_transcript import download_audio, _audio_extension, transcribe_audio, load_whisper_model


class TestAudioExtension(unittest.TestCase):
    def test_mp3_url(self):
        self.assertEqual(_audio_extension("https://cdn.example.com/ep.mp3"), ".mp3")

    def test_m4a_url(self):
        self.assertEqual(_audio_extension("https://cdn.example.com/ep.m4a"), ".m4a")

    def test_url_with_query_params(self):
        self.assertEqual(
            _audio_extension("https://cdn.example.com/ep.mp3?token=abc&format=m4a"),
            ".mp3",
        )

    def test_no_extension_defaults_to_mp3(self):
        self.assertEqual(_audio_extension("https://cdn.example.com/stream/12345"), ".mp3")

    def test_ogg_url(self):
        self.assertEqual(_audio_extension("https://cdn.example.com/ep.ogg"), ".ogg")


class TestDownloadAudio(unittest.TestCase):
    @patch("podcast_transcript.urllib.request.urlopen")
    def test_downloads_to_dest_dir(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [b"fake audio data", b""]
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        with TemporaryDirectory() as tmp:
            result = download_audio(
                "https://example.com/episode.mp3", Path(tmp), "ep123"
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.name.endswith(".mp3"))
            self.assertTrue(result.exists())

    @patch("podcast_transcript.urllib.request.urlopen")
    def test_returns_none_on_download_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Connection refused")
        with TemporaryDirectory() as tmp:
            result = download_audio(
                "https://example.com/fail.mp3", Path(tmp), "ep456"
            )
            self.assertIsNone(result)

    @patch("podcast_transcript.urllib.request.urlopen")
    def test_no_partial_file_on_failure(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("timeout")
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            download_audio("https://example.com/ep.mp3", dest, "ep789")
            files = list(dest.iterdir())
            self.assertEqual(files, [])

    @patch("podcast_transcript.urllib.request.urlopen")
    def test_skips_download_if_file_exists_and_nonempty(self, mock_urlopen):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            existing = dest / "podcast-ep123.mp3"
            existing.write_bytes(b"existing audio")
            result = download_audio(
                "https://example.com/ep.mp3", dest, "ep123"
            )
            self.assertEqual(result, existing)
            mock_urlopen.assert_not_called()


class TestDownloadAudioSecurity(unittest.TestCase):
    def test_rejects_file_scheme(self):
        with TemporaryDirectory() as tmp:
            result = download_audio("file:///etc/passwd", Path(tmp), "evil1")
            self.assertIsNone(result)

    def test_rejects_empty_scheme(self):
        with TemporaryDirectory() as tmp:
            result = download_audio("/some/local/path.mp3", Path(tmp), "evil2")
            self.assertIsNone(result)

    def test_accepts_https(self):
        pass  # covered by existing download tests


class TestDownloadAudioSizeLimit(unittest.TestCase):
    @patch("podcast_transcript.urllib.request.urlopen")
    def test_aborts_when_download_exceeds_limit(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"x" * 8192
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        import podcast_transcript
        original = podcast_transcript._MAX_DOWNLOAD_SIZE
        podcast_transcript._MAX_DOWNLOAD_SIZE = 8192 * 2
        try:
            with TemporaryDirectory() as tmp:
                result = download_audio(
                    "https://example.com/huge.mp3", Path(tmp), "huge1"
                )
                self.assertIsNone(result)
                files = [f for f in Path(tmp).iterdir() if not f.name.startswith(".")]
                self.assertEqual(len(files), 0)
        finally:
            podcast_transcript._MAX_DOWNLOAD_SIZE = original


class TestTranscribeAudio(unittest.TestCase):
    def test_returns_none_when_model_is_none(self):
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "test.mp3"
            audio.write_bytes(b"fake")
            result = transcribe_audio(audio, None)
            self.assertIsNone(result)

    def test_returns_transcript_on_success(self):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "text": "Hello world this is a test",
            "language": "en",
        }
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "test.mp3"
            audio.write_bytes(b"fake audio")
            result = transcribe_audio(audio, mock_model)
            self.assertEqual(result["text"], "Hello world this is a test")
            self.assertEqual(result["language"], "en")

    def test_returns_none_on_empty_text(self):
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {"text": "   ", "language": "en"}
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "test.mp3"
            audio.write_bytes(b"fake")
            result = transcribe_audio(audio, mock_model)
            self.assertIsNone(result)

    def test_returns_none_on_transcription_error(self):
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("CUDA error")
        with TemporaryDirectory() as tmp:
            audio = Path(tmp) / "test.mp3"
            audio.write_bytes(b"fake")
            result = transcribe_audio(audio, mock_model)
            self.assertIsNone(result)


class TestLoadWhisperModel(unittest.TestCase):
    def test_returns_model_on_success(self):
        mock_model = MagicMock()
        mock_whisper = MagicMock()
        mock_whisper.load_model.return_value = mock_model
        with patch.dict("sys.modules", {"whisper": mock_whisper}):
            result = load_whisper_model("base")
            self.assertEqual(result, mock_model)
            mock_whisper.load_model.assert_called_once_with("base")

    def test_returns_none_on_load_error(self):
        mock_whisper = MagicMock()
        mock_whisper.load_model.side_effect = RuntimeError("CUDA error")
        with patch.dict("sys.modules", {"whisper": mock_whisper}):
            result = load_whisper_model("base")
            self.assertIsNone(result)

    def test_returns_none_when_whisper_not_installed(self):
        with patch.dict("sys.modules", {"whisper": None}):
            result = load_whisper_model("base")
            self.assertIsNone(result)
