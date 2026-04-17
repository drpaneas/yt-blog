import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from autopublish import load_config


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_config(self, content: str) -> Path:
        p = self.tmp / "channels.toml"
        p.write_text(content)
        return p

    def test_loads_channels_and_paths(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/my-blog"
blog_content_dir = "content/post"
blog_branch = "main"
youtube_repo_dir = "/tmp/youtube"

[hugo]
categories = ["tech"]
tags = ["ai", "ml"]

[[channel]]
name = "Test Channel"
channel_id = "UCtest123"

[[channel]]
name = "Another"
channel_id = "UCother456"
"""))
        self.assertEqual(len(config["channels"]), 2)
        self.assertEqual(config["channels"][0]["name"], "Test Channel")
        self.assertTrue(config["blog_repo"].is_absolute())
        self.assertEqual(config["blog_content_dir"], "content/post")
        self.assertEqual(config["blog_branch"], "main")
        self.assertIsNone(config["llmwiki_dir"])
        self.assertEqual(config["hugo_categories"], ["tech"])
        self.assertEqual(config["hugo_tags"], ["ai", "ml"])

    def test_no_channels_returns_empty_list(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""))
        self.assertEqual(config["channels"], [])

    def test_defaults_for_optional_fields(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""))
        self.assertEqual(config["blog_content_dir"], "content/post")
        self.assertEqual(config["blog_branch"], "master")
        self.assertIsNone(config["llmwiki_dir"])
        self.assertEqual(config["hugo_categories"], ["youtube"])
        self.assertEqual(config["hugo_tags"], ["ai", "youtube"])

    def test_optional_llmwiki(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
llmwiki_dir = "/tmp/wiki"
"""))
        self.assertEqual(config["llmwiki_dir"], Path("/tmp/wiki").resolve())
