import os
import subprocess
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import youtube_fetch as fetch_module


class YoutubeFetchTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("YOUTUBE_TRANSCRIPT_IMPERSONATE", None)
        os.environ.pop("YOUTUBE_TRANSCRIPT_CACHE_DIR", None)

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
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                )

            self.assertEqual(result.path, expected_path)
            self.assertEqual(result.language, "en")

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
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                )

            self.assertEqual(result.path, expected_path)
            self.assertEqual(result.language, "en")

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
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    allow_non_english=True,
                )

            self.assertEqual(result.path, english_path)
            self.assertEqual(result.language, "en")
            self.assertTrue(english_path.exists())
            self.assertFalse(greek_path.exists())

    def test_keeps_only_one_english_track_when_multiple_english_vtts_fetched(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            english_a = output_dir / "partA.en.vtt"
            english_b = output_dir / "partB.en.vtt"

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                english_a.write_text("WEBVTT\n", encoding="utf-8")
                english_b.write_text("WEBVTT\n", encoding="utf-8")

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                )

            self.assertEqual(result.language, "en")
            self.assertTrue(result.path.exists())
            self.assertEqual(
                {path for path in output_dir.glob("*.vtt") if path.exists()},
                {result.path},
            )

    def test_en_orig_style_filename_treated_as_english(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            en_orig_path = output_dir / "video.en.orig.vtt"

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                en_orig_path.write_text("WEBVTT\n", encoding="utf-8")

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                )

            self.assertEqual(result.path, en_orig_path)
            self.assertEqual(result.language, "en")

    def test_broad_fallback_finds_english_when_narrow_attempt_wrote_no_subtitles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            english_path = output_dir / "clip.en.vtt"
            run_calls: list[int] = []

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                run_calls.append(1)
                if len(run_calls) == 1:
                    return None
                english_path.write_text("WEBVTT\n", encoding="utf-8")
                return None

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    allow_non_english=True,
                )

            self.assertEqual(len(run_calls), 2)
            self.assertEqual(result.path, english_path)
            self.assertEqual(result.language, "en")
            self.assertEqual(
                {path for path in output_dir.glob("*.vtt") if path.exists()},
                {english_path},
            )

    def test_fresh_vtt_files_collects_mtime_once_and_sorts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir)
            first = target_dir / "a.vtt"
            second = target_dir / "b.vtt"
            third = target_dir / "c.vtt"
            first.write_text("x", encoding="utf-8")
            second.write_text("x", encoding="utf-8")
            third.write_text("x", encoding="utf-8")
            base = os.stat(first).st_mtime_ns
            os.utime(second, ns=(base + 2_000_000_000, base + 2_000_000_000))
            os.utime(third, ns=(base + 1_000_000_000, base + 1_000_000_000))
            before = {first: base}
            fresh = fetch_module._fresh_vtt_files(target_dir, before)
            self.assertEqual(fresh, [third, second])

    def test_subtitle_language_skips_orig_metadata_segment(self) -> None:
        self.assertEqual(
            fetch_module._subtitle_language(Path("video.de.orig.vtt")),
            "de",
        )

    def test_is_likely_orig_track_does_not_match_original_substring(self) -> None:
        self.assertFalse(
            fetch_module._is_likely_orig_track(Path("video-my-original-title.de.vtt")),
        )

    def test_is_likely_orig_track_still_matches_dash_orig_and_dot_orig(self) -> None:
        self.assertTrue(fetch_module._is_likely_orig_track(Path("video.en.orig.vtt")))
        self.assertTrue(fetch_module._is_likely_orig_track(Path("clip-orig.ja.vtt")))

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

    def test_returns_non_english_result_when_opted_in(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            greek_path = output_dir / "video.el.vtt"
            run_calls: list[int] = []

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                run_calls.append(1)
                if len(run_calls) == 1:
                    return None
                greek_path.write_text("WEBVTT\n", encoding="utf-8")
                return None

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    allow_non_english=True,
                )

            self.assertEqual(len(run_calls), 2)
            self.assertEqual(result.path, greek_path)
            self.assertEqual(result.language, "el")
            self.assertTrue(greek_path.exists())

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

    def test_two_phase_english_then_broader_when_opted_in(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            de_path = output_dir / "video.de.vtt"
            run_calls: list[list[str]] = []

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                run_calls.append(list(command))
                if len(run_calls) == 1:
                    self.assertIn("--sub-langs", command)
                    self.assertIn("en", command)
                    return None
                de_path.write_text("WEBVTT\n", encoding="utf-8")
                self.assertIn("--sub-langs", command)
                self.assertNotEqual(
                    command[command.index("--sub-langs") + 1],
                    "en",
                )
                return None

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    allow_non_english=True,
                )

            self.assertEqual(len(run_calls), 2)
            self.assertEqual(result.path, de_path)
            self.assertEqual(result.language, "de")
            self.assertTrue(de_path.exists())

    def test_prefers_orig_track_then_language_and_filename_order(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            fr_path = output_dir / "video.fr.vtt"
            orig_ja_path = output_dir / "video.orig.ja.vtt"
            phase = [0]

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                phase[0] += 1
                if phase[0] == 1:
                    return None
                fr_path.write_text("WEBVTT\n", encoding="utf-8")
                orig_ja_path.write_text("WEBVTT\n", encoding="utf-8")
                return None

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    allow_non_english=True,
                )

            self.assertEqual(result.path, orig_ja_path)
            self.assertEqual(result.language, "ja")
            self.assertTrue(orig_ja_path.exists())
            self.assertFalse(fr_path.exists())

    def test_non_english_selection_sorts_by_language_then_filename(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            fr_path = output_dir / "z.fr.vtt"
            de_path = output_dir / "a.de.vtt"
            phase = [0]

            def fake_run(command, cwd, check, capture_output, text):
                self.assertIn("yt-dlp", command[0])
                self.assertEqual(cwd, output_dir)
                self.assertTrue(check)
                self.assertTrue(capture_output)
                self.assertTrue(text)
                phase[0] += 1
                if phase[0] == 1:
                    return None
                fr_path.write_text("WEBVTT\n", encoding="utf-8")
                de_path.write_text("WEBVTT\n", encoding="utf-8")
                return None

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                result = fetch_module.fetch_auto_sub_vtt(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    allow_non_english=True,
                )

            self.assertEqual(result.path, de_path)
            self.assertEqual(result.language, "de")
            self.assertTrue(de_path.exists())
            self.assertFalse(fr_path.exists())


    def test_auto_sub_attempt_retries_once_on_429_then_succeeds(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected_path = output_dir / "video.en.vtt"
            calls: list[int] = []

            def fake_run(command, cwd, check, capture_output, text):
                calls.append(1)
                if len(calls) == 1:
                    raise subprocess.CalledProcessError(
                        1,
                        command,
                        stderr="HTTP Error 429: Too Many Requests",
                    )
                expected_path.write_text("WEBVTT\n", encoding="utf-8")
                return CompletedProcess(command, 0)

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                with patch.object(fetch_module.time, "sleep") as mock_sleep:
                    fresh, err = fetch_module._fetch_auto_sub_attempt(
                        output_dir,
                        "https://www.youtube.com/watch?v=abc123",
                        fetch_module._SUB_LANGS_ENGLISH_ONLY,
                    )

            self.assertEqual(len(calls), 2)
            self.assertIsNone(err)
            self.assertEqual(fresh, [expected_path])
            mock_sleep.assert_called_once()

    def test_auto_sub_attempt_does_not_retry_on_non_429_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            calls: list[int] = []

            def fake_run(command, cwd, check, capture_output, text):
                calls.append(1)
                raise subprocess.CalledProcessError(
                    1,
                    command,
                    stderr="HTTP Error 403: Forbidden",
                )

            with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                with patch.object(fetch_module.time, "sleep") as mock_sleep:
                    fresh, err = fetch_module._fetch_auto_sub_attempt(
                        output_dir,
                        "https://www.youtube.com/watch?v=abc123",
                        fetch_module._SUB_LANGS_ENGLISH_ONLY,
                    )

            self.assertEqual(len(calls), 1)
            self.assertIsNotNone(err)
            self.assertEqual(err.returncode, 1)
            mock_sleep.assert_not_called()
            self.assertEqual(fresh, [])

    def test_impersonate_env_appends_to_ytdlp_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            expected_path = output_dir / "video.en.vtt"
            commands: list[list[str]] = []

            def fake_run(command, cwd, check, capture_output, text):
                commands.append(list(command))
                expected_path.write_text("WEBVTT\n", encoding="utf-8")
                return CompletedProcess(command, 0)

            with patch.dict(os.environ, {"YOUTUBE_TRANSCRIPT_IMPERSONATE": "chrome"}):
                with patch.object(fetch_module.subprocess, "run", side_effect=fake_run):
                    fetch_module.fetch_auto_sub_vtt(
                        "https://www.youtube.com/watch?v=abc123def45",
                        output_dir,
                    )

            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][:4], ["yt-dlp", "--impersonate", "chrome", "--write-auto-subs"])

    def test_cache_hit_returns_cached_vtt_without_subprocess_run(self) -> None:
        with TemporaryDirectory() as cache_dir:
            with TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                cache_root = Path(cache_dir)
                cached_file = cache_root / "abc123def45-en.vtt"
                cached_file.write_text("WEBVTT\nNOTE cached\n", encoding="utf-8")

                def must_not_run(*_args, **_kwargs):
                    raise AssertionError("subprocess.run should not be called on cache hit")

                with patch.dict(os.environ, {"YOUTUBE_TRANSCRIPT_CACHE_DIR": str(cache_root)}):
                    with patch.object(fetch_module.subprocess, "run", side_effect=must_not_run):
                        result = fetch_module.fetch_auto_sub_vtt(
                            "https://www.youtube.com/watch?v=abc123def45",
                            output_dir,
                        )

                self.assertEqual(result.path, cached_file)
                self.assertEqual(result.language, "en")
                self.assertFalse(result.used_fallback)

    def test_cache_hit_allow_non_english_returns_metadata_from_filename(self) -> None:
        with TemporaryDirectory() as cache_dir:
            with TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                cache_root = Path(cache_dir)
                cached_file = cache_root / "abc123def45-allow-non-english-el-1.vtt"
                cached_file.write_text("WEBVTT\n", encoding="utf-8")

                def must_not_run(*_args, **_kwargs):
                    raise AssertionError("subprocess.run should not be called on cache hit")

                with patch.dict(os.environ, {"YOUTUBE_TRANSCRIPT_CACHE_DIR": str(cache_root)}):
                    with patch.object(fetch_module.subprocess, "run", side_effect=must_not_run):
                        result = fetch_module.fetch_auto_sub_vtt(
                            "https://www.youtube.com/watch?v=abc123def45",
                            output_dir,
                            allow_non_english=True,
                        )

                self.assertEqual(result.path, cached_file)
                self.assertEqual(result.language, "el")
                self.assertTrue(result.used_fallback)

    def test_cache_hit_allow_non_english_hyphenated_language_tag_metadata(self) -> None:
        with TemporaryDirectory() as cache_dir:
            with TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)
                cache_root = Path(cache_dir)
                cached_file = cache_root / "abc123def45-allow-non-english-zh-hans-0.vtt"
                cached_file.write_text("WEBVTT\n", encoding="utf-8")

                def must_not_run(*_args, **_kwargs):
                    raise AssertionError("subprocess.run should not be called on cache hit")

                with patch.dict(os.environ, {"YOUTUBE_TRANSCRIPT_CACHE_DIR": str(cache_root)}):
                    with patch.object(fetch_module.subprocess, "run", side_effect=must_not_run):
                        result = fetch_module.fetch_auto_sub_vtt(
                            "https://www.youtube.com/watch?v=abc123def45",
                            output_dir,
                            allow_non_english=True,
                        )

                self.assertEqual(result.path, cached_file)
                self.assertEqual(result.language, "zh-hans")
                self.assertFalse(result.used_fallback)

                cached_file.unlink()
                cached_fb = cache_root / "abc123def45-allow-non-english-zh-hans-1.vtt"
                cached_fb.write_text("WEBVTT\n", encoding="utf-8")
                with patch.dict(os.environ, {"YOUTUBE_TRANSCRIPT_CACHE_DIR": str(cache_root)}):
                    with patch.object(fetch_module.subprocess, "run", side_effect=must_not_run):
                        result_fb = fetch_module.fetch_auto_sub_vtt(
                            "https://www.youtube.com/watch?v=abc123def45",
                            output_dir,
                            allow_non_english=True,
                        )

                self.assertEqual(result_fb.path, cached_fb)
                self.assertEqual(result_fb.language, "zh-hans")
                self.assertTrue(result_fb.used_fallback)
