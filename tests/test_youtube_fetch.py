import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import youtube_fetch as fetch_module


class YoutubeFetchTests(unittest.TestCase):
    def test_returns_new_vtt_path_after_ytdlp_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected_path = output_dir / "video.en.vtt"

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                expected_path.write_text("WEBVTT\n", encoding="utf-8")

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                resolved_path = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                )

            self.assertEqual(resolved_path, expected_path)

    def test_raises_clear_error_when_ytdlp_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(fetch_module.subprocess, "run", side_effect=FileNotFoundError()):
                with self.assertRaisesRegex(RuntimeError, "yt-dlp"):
                    fetch_module.fetch_auto_sub_vtt(
                        "https://www.youtube.com/watch?v=abc123",
                        Path(temp_dir),
                    )

    def test_returns_english_vtt_when_ytdlp_errors_after_writing_it(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected_path = output_dir / "video.en.vtt"

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                expected_path.write_text("WEBVTT\n", encoding="utf-8")
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=command,
                    stderr="HTTP Error 429: Too Many Requests",
                )

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                resolved_path = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                )

            self.assertEqual(resolved_path, expected_path)

    def test_keeps_english_vtt_and_deletes_other_fresh_subtitles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            english_path = output_dir / "video.en.vtt"
            greek_path = output_dir / "video.el.vtt"

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                english_path.write_text("WEBVTT\n", encoding="utf-8")
                greek_path.write_text("WEBVTT\n", encoding="utf-8")

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                resolved_path = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                )

            self.assertEqual(resolved_path, english_path)
            self.assertTrue(english_path.exists())
            self.assertFalse(greek_path.exists())

    def test_raises_clear_error_when_only_non_english_vtt_is_created(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            greek_path = output_dir / "video.el.vtt"

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                greek_path.write_text("WEBVTT\n", encoding="utf-8")
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=command,
                    stderr="HTTP Error 429: Too Many Requests",
                )

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "English subtitles unavailable"):
                    fetch_module.fetch_auto_sub_vtt(
                        "https://www.youtube.com/watch?v=abc123",
                        output_dir,
                    )

            self.assertFalse(greek_path.exists())

    def test_raises_when_ytdlp_creates_no_vtt_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "no new \\.vtt subtitle file was created"):
                    fetch_module.fetch_auto_sub_vtt(
                        "https://www.youtube.com/watch?v=abc123",
                        output_dir,
                    )
