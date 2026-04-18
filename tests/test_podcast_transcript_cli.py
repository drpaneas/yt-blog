import unittest

from podcast_transcript_cli import _extract_podcast_id


class TestExtractPodcastIdCli(unittest.TestCase):
    def test_full_url(self):
        pid, eid = _extract_podcast_id("https://podcastindex.org/podcast/6958769")
        self.assertEqual(pid, "6958769")
        self.assertIsNone(eid)

    def test_url_with_episode(self):
        pid, eid = _extract_podcast_id(
            "https://podcastindex.org/podcast/6958769?episode=53451816130"
        )
        self.assertEqual(pid, "6958769")
        self.assertEqual(eid, "53451816130")

    def test_raw_id(self):
        pid, eid = _extract_podcast_id("6958769")
        self.assertEqual(pid, "6958769")
        self.assertIsNone(eid)

    def test_invalid_url(self):
        with self.assertRaises(ValueError) as ctx:
            _extract_podcast_id("https://spotify.com/episode/abc")
        self.assertIn("Only PodcastIndex URLs are supported", str(ctx.exception))

    def test_url_with_extra_query_params(self):
        pid, eid = _extract_podcast_id(
            "https://podcastindex.org/podcast/6958769?episode=12345&foo=bar"
        )
        self.assertEqual(pid, "6958769")
        self.assertEqual(eid, "12345")

    def test_url_without_episode_param(self):
        pid, eid = _extract_podcast_id(
            "https://podcastindex.org/podcast/6958769?foo=bar"
        )
        self.assertEqual(pid, "6958769")
        self.assertIsNone(eid)

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            _extract_podcast_id("")

    def test_non_podcastindex_url_raises(self):
        with self.assertRaises(ValueError):
            _extract_podcast_id("https://example.com/podcast/123")
