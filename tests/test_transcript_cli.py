import io
import json
import os
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import ANY, patch

import transcript_cli as cli_module
from youtube_fetch import SubtitleFetchResult


def _sample_vtt_body() -> str:
    return textwrap.dedent(
        """\
        WEBVTT

        00:00:00.000 --> 00:00:01.000
        Hello

        00:00:01.000 --> 00:00:02.000
        Hello world.
        """
    )


def _fetch_writes_vtt(
    url: str,
    output_dir: Path,
    *,
    allow_non_english: bool = False,
    language: str = "en",
    filename: str = "downloaded.en.vtt",
    body: str | None = None,
    used_fallback: bool = False,
) -> SubtitleFetchResult:
    _ = url
    _ = allow_non_english
    p = Path(output_dir) / filename
    p.write_text(body if body is not None else _sample_vtt_body(), encoding="utf-8")
    return SubtitleFetchResult(path=p, language=language, used_fallback=used_fallback)


class TranscriptCliTests(unittest.TestCase):
    def test_main_writes_cleaned_sibling_file_for_local_vtt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vtt_path = Path(temp_dir) / "sample.en.vtt"
            vtt_path.write_text(
                textwrap.dedent(
                    """\
                    WEBVTT

                    00:00:00.000 --> 00:00:01.000
                    Hello

                    00:00:01.000 --> 00:00:02.000
                    Hello world.
                    """
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_module.main([str(vtt_path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(vtt_path.with_suffix(".clean.txt").read_text(encoding="utf-8").strip(), "Hello world.")

    def test_main_uses_url_workflow_and_prints_cleaned_text(self) -> None:
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "fetch_auto_sub_vtt",
            side_effect=lambda url, od, **kw: _fetch_writes_vtt(url, od),
        ) as fetch_mock:
            with redirect_stdout(stdout):
                exit_code = cli_module.main(["https://www.youtube.com/watch?v=abc123", "--stdout"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "Hello world.")
        self.assertEqual(fetch_mock.call_count, 1)
        call_args = fetch_mock.call_args
        self.assertEqual(call_args[0][0], "https://www.youtube.com/watch?v=abc123")
        self.assertNotEqual(call_args[0][1], Path.cwd())

    def test_main_prefers_url_workflow_for_vtt_suffix_urls(self) -> None:
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "fetch_auto_sub_vtt",
            side_effect=lambda url, od, **kw: _fetch_writes_vtt(url, od),
        ) as fetch_mock:
            with redirect_stdout(stdout):
                exit_code = cli_module.main(["https://example.com/subtitles.vtt", "--stdout"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "Hello world.")
        fetch_mock.assert_called_once_with(
            "https://example.com/subtitles.vtt",
            ANY,
            allow_non_english=False,
        )

    def test_main_default_url_mode_rejects_non_english_subtitles(self) -> None:
        stderr = io.StringIO()
        with patch.object(
            cli_module,
            "fetch_auto_sub_vtt",
            side_effect=RuntimeError("English subtitles unavailable; found subtitle languages: el."),
        ) as fetch_mock:
            with redirect_stderr(stderr):
                exit_code = cli_module.main(["https://www.youtube.com/watch?v=abc123", "--stdout"])

        self.assertEqual(exit_code, 1)
        self.assertIn("English subtitles unavailable", stderr.getvalue())
        self.assertEqual(fetch_mock.call_count, 1)
        self.assertNotEqual(fetch_mock.call_args[0][1], Path.cwd())

    def test_main_allows_non_english_url_mode_when_opted_in(self) -> None:
        el_body = textwrap.dedent(
            """\
            WEBVTT

            00:00:00.000 --> 00:00:01.000
            Γεια

            00:00:01.000 --> 00:00:02.000
            Γεια σου.
            """
        )
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "fetch_auto_sub_vtt",
            side_effect=lambda url, od, **kw: _fetch_writes_vtt(
                url, od, language="el", filename="downloaded.el.vtt", body=el_body
            ),
        ) as fetch_mock:
            with redirect_stdout(stdout):
                exit_code = cli_module.main(
                    ["https://www.youtube.com/watch?v=abc123", "--stdout", "--allow-non-english"]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue().strip(), "Γεια σου.")
        fetch_mock.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc123",
            ANY,
            allow_non_english=True,
        )

    def test_main_json_output_includes_cleaned_text_and_language(self) -> None:
        el_body = textwrap.dedent(
            """\
            WEBVTT

            00:00:00.000 --> 00:00:01.000
            Γεια

            00:00:01.000 --> 00:00:02.000
            Γεια σου.
            """
        )
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "fetch_auto_sub_vtt",
            side_effect=lambda url, od, **kw: _fetch_writes_vtt(
                url,
                od,
                language="el",
                filename="downloaded.el.vtt",
                body=el_body,
                used_fallback=True,
            ),
        ):
            with redirect_stdout(stdout):
                exit_code = cli_module.main(
                    [
                        "https://www.youtube.com/watch?v=abc123",
                        "--allow-non-english",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["language"], "el")
        self.assertEqual(payload["text"], "Γεια σου.")
        self.assertTrue(payload["used_fallback"])

    def test_main_rejects_invalid_input(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = cli_module.main(["not-a-url-or-vtt"])

        self.assertEqual(exit_code, 1)
        self.assertIn("URL or a .vtt file path", stderr.getvalue())

    def test_url_workflow_passes_temporary_directory_to_fetch_not_cwd(self) -> None:
        """URL subtitle fetch must use a temp dir so files are not written to the repo root."""
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "fetch_auto_sub_vtt",
            side_effect=lambda url, od, **kw: _fetch_writes_vtt(url, od),
        ) as fetch_mock:
            with redirect_stdout(stdout):
                exit_code = cli_module.main(["https://www.youtube.com/watch?v=abc123", "--stdout"])

        self.assertEqual(exit_code, 0)
        fetch_mock.assert_called_once_with(
            "https://www.youtube.com/watch?v=abc123",
            ANY,
            allow_non_english=False,
        )
        out_dir = fetch_mock.call_args[0][1]
        self.assertNotEqual(out_dir, Path.cwd())

    def test_main_json_includes_used_fallback_for_url_fetch(self) -> None:
        stdout = io.StringIO()
        with patch.object(
            cli_module,
            "fetch_auto_sub_vtt",
            side_effect=lambda url, od, **kw: _fetch_writes_vtt(url, od, used_fallback=True),
        ):
            with redirect_stdout(stdout):
                exit_code = cli_module.main(
                    ["https://www.youtube.com/watch?v=abc123", "--json"]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("used_fallback", payload)
        self.assertTrue(payload["used_fallback"])

    def test_main_json_sets_used_fallback_false_for_local_vtt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vtt_path = Path(temp_dir) / "sample.en.vtt"
            vtt_path.write_text(
                textwrap.dedent(
                    """\
                    WEBVTT

                    00:00:00.000 --> 00:00:01.000
                    Hello world.
                    """
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_module.main([str(vtt_path), "--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIn("used_fallback", payload)
        self.assertFalse(payload["used_fallback"])

    def test_main_url_default_writes_clean_txt_to_cwd_not_temp(self) -> None:
        with TemporaryDirectory() as temp_dir:
            prev = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.object(
                    cli_module,
                    "fetch_auto_sub_vtt",
                    side_effect=lambda url, od, **kw: _fetch_writes_vtt(
                        url, od, filename="video.en.vtt"
                    ),
                ):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        exit_code = cli_module.main(["https://www.youtube.com/watch?v=abc123"])
            finally:
                os.chdir(prev)

            self.assertEqual(exit_code, 0)
            out_line = stdout.getvalue().strip()
            out_path = Path(out_line)
            self.assertTrue(out_path.is_absolute())
            self.assertEqual(out_path.parent.resolve(), Path(temp_dir).resolve())
            self.assertEqual(out_path.name, "video.en.clean.txt")
            self.assertEqual(out_path.read_text(encoding="utf-8").strip(), "Hello world.")

    def test_main_local_vtt_skips_orig_segment_for_language(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vtt_path = Path(temp_dir) / "clip.orig.en.vtt"
            vtt_path.write_text(
                textwrap.dedent(
                    """\
                    WEBVTT

                    00:00:00.000 --> 00:00:01.000
                    Hello world.
                    """
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = cli_module.main([str(vtt_path), "--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["language"], "en")
