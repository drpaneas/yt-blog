import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
import json

from podcast_autopublish import load_config, _find_existing_blog
from podcast_fetch import extract_podcast_id


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

    def test_state_dir_default(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""))
        from publish_utils import DEFAULT_STATE_DIR
        self.assertEqual(config["state_dir"], DEFAULT_STATE_DIR)

    def test_state_dir_custom(self):
        config = load_config(self._write_config("""
state_dir = "/tmp/my-state"

[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""))
        self.assertEqual(config["state_dir"], Path("/tmp/my-state").resolve())

    def test_no_podcasts_returns_empty_list(self):
        config = load_config(self._write_config("""
[paths]
blog_repo = "~/blog"
youtube_repo_dir = "/tmp/yt"
"""))
        self.assertEqual(config["podcasts"], [])

    def test_blog_repo_optional(self):
        config = load_config(self._write_config("""
[paths]
youtube_repo_dir = "/tmp/yt"
"""))
        self.assertIsNone(config["blog_repo"])
        self.assertIsNone(config["blog_content_dir"])
        self.assertIsNone(config["blog_branch"])


class TestExtractPodcastId(unittest.TestCase):
    def test_full_url(self):
        pid, eid = extract_podcast_id(
            "https://podcastindex.org/podcast/6958769"
        )
        self.assertEqual(pid, "6958769")
        self.assertIsNone(eid)

    def test_url_with_episode_param(self):
        pid, eid = extract_podcast_id(
            "https://podcastindex.org/podcast/6958769?episode=12345"
        )
        self.assertEqual(pid, "6958769")
        self.assertEqual(eid, "12345")

    def test_raw_numeric_id(self):
        pid, eid = extract_podcast_id("6958769")
        self.assertEqual(pid, "6958769")
        self.assertIsNone(eid)

    def test_invalid_url_raises_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            extract_podcast_id("https://spotify.com/episode/abc")
        self.assertIn("Only PodcastIndex URLs are supported", str(ctx.exception))
        self.assertIn("podcastindex.org", str(ctx.exception))

    def test_direct_audio_url_raises_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            extract_podcast_id(
                "https://audio.buzzsprout.com/gtmp94ahf022qgcjujcupynqf6gq"
            )
        self.assertIn("Only PodcastIndex URLs are supported", str(ctx.exception))


class TestFindExistingBlog(unittest.TestCase):
    def test_finds_matching_file(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            f = d / "podcast-blog-test-episode-12345.md"
            f.write_text("# Test")
            result = _find_existing_blog("12345", d)
            self.assertEqual(result, f)

    def test_returns_none_when_no_match(self):
        with TemporaryDirectory() as tmp:
            result = _find_existing_blog("99999", Path(tmp))
            self.assertIsNone(result)

    def test_returns_none_for_nonexistent_dir(self):
        result = _find_existing_blog("12345", Path("/nonexistent/dir"))
        self.assertIsNone(result)


class TestGenerateBlogPost(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    @patch("podcast_autopublish.subprocess.run")
    def test_passes_episode_id_in_prompt(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        blog_file = self.tmp / "podcast-blog-test-title-12345.md"
        blog_file.write_text("# Test")

        from podcast_autopublish import generate_blog_post
        transcript = {"text": "hello", "language": "en"}
        generate_blog_post(transcript, "12345", "https://example.com/ep", self.tmp)

        call_args = mock_run.call_args[0][0]
        prompt_arg = call_args[2]
        self.assertIn("--episode-id 12345", prompt_arg)

    @patch("podcast_autopublish.subprocess.run")
    @patch("podcast_autopublish.time")
    def test_fallback_finds_timestamp_named_file(self, mock_time, mock_run):
        """When Claude names the file with a timestamp instead of episode ID,
        generate_blog_post should still find it via recency fallback."""
        mock_time.time.return_value = 1000000000.0
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        blog_file = self.tmp / "podcast-blog-some-title-20260418-163000.md"
        blog_file.write_text("# Test")
        import os
        os.utime(blog_file, (1000000005.0, 1000000005.0))

        from podcast_autopublish import generate_blog_post
        transcript = {"text": "hello", "language": "en"}
        result = generate_blog_post(transcript, "12345", "https://example.com/ep", self.tmp)

        self.assertIsNotNone(result)
        self.assertEqual(result.name, "podcast-blog-some-title-20260418-163000.md")

    @patch("podcast_autopublish.subprocess.run")
    @patch("podcast_autopublish.time")
    def test_fallback_ignores_preexisting_files(self, mock_time, mock_run):
        """Fallback should not pick up podcast-blog files that existed before
        the subprocess call (they belong to other episodes)."""
        mock_time.time.return_value = 9999999999.0
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        old_file = self.tmp / "podcast-blog-old-episode-99999.md"
        old_file.write_text("# Old")
        import os
        os.utime(old_file, (1000000000.0, 1000000000.0))

        from podcast_autopublish import generate_blog_post
        transcript = {"text": "hello", "language": "en"}
        result = generate_blog_post(transcript, "12345", "https://example.com/ep", self.tmp)

        self.assertIsNone(result)


class TestPublishEpisodeNoBlog(unittest.TestCase):
    """_publish_episode should succeed and return title when blog_repo is None."""

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_returns_title_and_success_without_blog(self):
        blog_file = self.tmp / "podcast-blog-test-ep-12345.md"
        blog_file.write_text("# My Episode Title\n\nContent here.")

        from podcast_autopublish import _publish_episode
        title, success = _publish_episode(
            episode_id="12345",
            blog_path=blog_file,
            podcast_name="Test Pod",
            blog_repo=None,
            blog_content_dir=None,
            llmwiki_dir=None,
            title="Fallback Title",
        )

        self.assertTrue(success)
        self.assertEqual(title, "My Episode Title")

    def test_copies_to_wiki_without_blog(self):
        blog_file = self.tmp / "podcast-blog-test-ep-12345.md"
        blog_file.write_text("# Title\n\nContent.")
        wiki_dir = self.tmp / "wiki"
        wiki_dir.mkdir()
        (wiki_dir / "raw").mkdir()

        from podcast_autopublish import _publish_episode
        title, success = _publish_episode(
            episode_id="12345",
            blog_path=blog_file,
            podcast_name="Test Pod",
            blog_repo=None,
            blog_content_dir=None,
            llmwiki_dir=wiki_dir,
            title="Fallback",
        )

        self.assertTrue(success)
        wiki_file = wiki_dir / "raw" / "podcast-blog-test-ep-12345.md"
        self.assertTrue(wiki_file.exists())


class TestRunNoBlog(unittest.TestCase):
    """Podcast run functions should work without blog_repo."""

    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_config(self, content: str) -> Path:
        p = self.tmp / "channels.toml"
        p.write_text(content)
        return p

    def test_load_config_no_blog(self):
        config = load_config(self._write_config("""
[paths]
youtube_repo_dir = "/tmp/yt"

[[podcast]]
name = "Test Pod"
podcast_id = "123"
"""))
        self.assertIsNone(config["blog_repo"])
        self.assertEqual(len(config["podcasts"]), 1)
