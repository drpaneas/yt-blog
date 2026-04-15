import io
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import transcript_cli as cli_module


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
        with TemporaryDirectory() as temp_dir:
            vtt_path = Path(temp_dir) / "downloaded.en.vtt"
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
            with patch.object(cli_module, "fetch_auto_sub_vtt", return_value=vtt_path):
                with redirect_stdout(stdout):
                    exit_code = cli_module.main(["https://www.youtube.com/watch?v=abc123", "--stdout"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue().strip(), "Hello world.")

    def test_main_prefers_url_workflow_for_vtt_suffix_urls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            vtt_path = Path(temp_dir) / "downloaded.en.vtt"
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
            with patch.object(cli_module, "fetch_auto_sub_vtt", return_value=vtt_path) as fetch_mock:
                with redirect_stdout(stdout):
                    exit_code = cli_module.main(["https://example.com/subtitles.vtt", "--stdout"])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue().strip(), "Hello world.")
            fetch_mock.assert_called_once_with("https://example.com/subtitles.vtt", Path.cwd())

    def test_main_rejects_invalid_input(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = cli_module.main(["not-a-url-or-vtt"])

        self.assertEqual(exit_code, 1)
        self.assertIn("URL or a .vtt file path", stderr.getvalue())
