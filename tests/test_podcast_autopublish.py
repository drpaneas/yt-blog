import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from podcast_autopublish import load_config, _extract_podcast_id


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

    def test_loads_podcast_entries(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/my-blog"
youtube_repo_dir = "/tmp/youtube"

[[podcast]]
name = "Test Podcast"
podcast_id = "123456"

[[podcast]]
name = "Another Pod"
podcast_id = "789012"
"""))
        self.assertEqual(len(config["podcasts"]), 2)
        self.assertEqual(config["podcasts"][0]["name"], "Test Podcast")
        self.assertEqual(config["podcasts"][0]["podcast_id"], "123456")

    def test_loads_podcast_hugo_config(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/my-blog"
youtube_repo_dir = "/tmp/youtube"

[podcast_hugo]
categories = ["shows"]
tags = ["tech", "podcast"]
"""))
        self.assertEqual(config["podcast_hugo_categories"], ["shows"])
        self.assertEqual(config["podcast_hugo_tags"], ["tech", "podcast"])

    def test_podcast_hugo_defaults(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""))
        self.assertEqual(config["podcast_hugo_categories"], ["podcast"])
        self.assertEqual(config["podcast_hugo_tags"], [])

    def test_no_podcasts_returns_empty_list(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""))
        self.assertEqual(config["podcasts"], [])


class TestExtractPodcastId(unittest.TestCase):
    def test_full_url(self):
        pid, eid = _extract_podcast_id(
            "https://podcastindex.org/podcast/6958769"
        )
        self.assertEqual(pid, "6958769")
        self.assertIsNone(eid)

    def test_url_with_episode_param(self):
        pid, eid = _extract_podcast_id(
            "https://podcastindex.org/podcast/6958769?episode=12345"
        )
        self.assertEqual(pid, "6958769")
        self.assertEqual(eid, "12345")

    def test_raw_numeric_id(self):
        pid, eid = _extract_podcast_id("6958769")
        self.assertEqual(pid, "6958769")
        self.assertIsNone(eid)

    def test_invalid_url_raises_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            _extract_podcast_id("https://spotify.com/episode/abc")
        self.assertIn("Only PodcastIndex URLs are supported", str(ctx.exception))
        self.assertIn("podcastindex.org", str(ctx.exception))

    def test_direct_audio_url_raises_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            _extract_podcast_id(
                "https://audio.buzzsprout.com/gtmp94ahf022qgcjujcupynqf6gq"
            )
        self.assertIn("Only PodcastIndex URLs are supported", str(ctx.exception))
