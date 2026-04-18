import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from publish_utils import push_blog_repo, slugify, verify_blog_repo


class TestSlugify(unittest.TestCase):
    def test_simple_name(self):
        self.assertEqual(slugify("My Channel"), "my-channel")

    def test_special_characters(self):
        self.assertEqual(slugify("Tech @ Home!"), "tech-home")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "unknown")

    def test_unicode_only(self):
        self.assertEqual(slugify("日本語"), "unknown")

    def test_already_slugified(self):
        self.assertEqual(slugify("my-channel"), "my-channel")

    def test_extra_whitespace(self):
        self.assertEqual(slugify("  lots   of   spaces  "), "lots-of-spaces")


class TestVerifyBlogRepo(unittest.TestCase):
    @patch("publish_utils.subprocess.run")
    def test_raises_on_wrong_branch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="develop\n", stderr="")
        with self.assertRaises(RuntimeError) as ctx:
            verify_blog_repo(Path("/fake/repo"), "main")
        self.assertIn("develop", str(ctx.exception))

    @patch("publish_utils.subprocess.run")
    def test_raises_on_uncommitted_changes(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main\n", stderr=""),
            MagicMock(returncode=0, stdout="M file.txt\n", stderr=""),
        ]
        with self.assertRaises(RuntimeError) as ctx:
            verify_blog_repo(Path("/fake/repo"), "main")
        self.assertIn("uncommitted", str(ctx.exception))

    @patch("publish_utils.subprocess.run")
    def test_passes_on_clean_correct_branch(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="main\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        verify_blog_repo(Path("/fake/repo"), "main")

    @patch("publish_utils.subprocess.run")
    def test_raises_on_non_git_directory(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="not a git repo")
        with self.assertRaises(RuntimeError) as ctx:
            verify_blog_repo(Path("/not/a/repo"), "main")
        self.assertIn("not a valid git repository", str(ctx.exception))


class TestPushBlogRepo(unittest.TestCase):
    @patch("publish_utils.subprocess.run")
    def test_returns_true_on_successful_commit(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout="M file.md\n"),
            MagicMock(returncode=0),
        ]
        result = push_blog_repo(
            Path("/fake/blog"), Path("/fake/blog/content/test.md"), ["Test Post"]
        )
        self.assertTrue(result)

    @patch("publish_utils.subprocess.run")
    def test_returns_true_when_nothing_to_commit(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0, stdout=""),
        ]
        result = push_blog_repo(
            Path("/fake/blog"), Path("/fake/blog/content/test.md"), ["Test Post"]
        )
        self.assertTrue(result)
