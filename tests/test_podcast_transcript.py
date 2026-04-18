import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
from io import BytesIO

from podcast_transcript import download_audio, _audio_extension


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

    def test_skips_download_if_file_exists_and_nonempty(self):
        with TemporaryDirectory() as tmp:
            dest = Path(tmp)
            existing = dest / "podcast-ep123.mp3"
            existing.write_bytes(b"existing audio")
            result = download_audio(
                "https://example.com/ep.mp3", dest, "ep123"
            )
            self.assertEqual(result, existing)


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
