import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from autopublish import load_config


class TestLoadConfig(unittest.TestCase):
    def test_loads_channels_and_paths(self):
        toml_content = """
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
"""
        with NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config = load_config(Path(f.name))

        self.assertEqual(len(config["channels"]), 2)
        self.assertEqual(config["channels"][0]["name"], "Test Channel")
        self.assertTrue(config["blog_repo"].is_absolute())
        self.assertEqual(config["blog_content_dir"], "content/post")
        self.assertEqual(config["blog_branch"], "main")
        self.assertIsNone(config["llmwiki_dir"])
        self.assertEqual(config["hugo_categories"], ["tech"])
        self.assertEqual(config["hugo_tags"], ["ai", "ml"])

    def test_no_channels_returns_empty_list(self):
        toml_content = """
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""
        with NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config = load_config(Path(f.name))

        self.assertEqual(config["channels"], [])

    def test_defaults_for_optional_fields(self):
        toml_content = """
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""
        with NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config = load_config(Path(f.name))

        self.assertEqual(config["blog_content_dir"], "content/post")
        self.assertEqual(config["blog_branch"], "master")
        self.assertIsNone(config["llmwiki_dir"])
        self.assertEqual(config["hugo_categories"], ["youtube"])
        self.assertEqual(config["hugo_tags"], ["ai", "youtube"])

    def test_optional_llmwiki(self):
        toml_content = """
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
llmwiki_dir = "/tmp/wiki"
"""
        with NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            config = load_config(Path(f.name))

        self.assertEqual(config["llmwiki_dir"], Path("/tmp/wiki").resolve())
