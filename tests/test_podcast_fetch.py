import hashlib
import unittest
import urllib.error
from unittest.mock import patch

from podcast_fetch import _podcastindex_headers, fetch_episodes, fetch_new_episodes


class TestPodcastIndexHeaders(unittest.TestCase):
    @patch("podcast_fetch.time")
    @patch("podcast_fetch.os")
    def test_headers_contain_required_fields(self, mock_os, mock_time):
        mock_os.environ = {
            "PODCASTINDEX_API_KEY": "testkey123",
            "PODCASTINDEX_API_SECRET": "testsecret456",
        }
        mock_time.time.return_value = 1700000000
        headers = _podcastindex_headers()
        self.assertEqual(headers["X-Auth-Key"], "testkey123")
        self.assertEqual(headers["X-Auth-Date"], "1700000000")
        expected_hash = hashlib.sha1(
            b"testkey123testsecret4561700000000"
        ).hexdigest()
        self.assertEqual(headers["Authorization"], expected_hash)
        self.assertIn("User-Agent", headers)

    @patch("podcast_fetch.os")
    def test_raises_when_key_missing(self, mock_os):
        mock_os.environ = {}
        with self.assertRaises(RuntimeError):
            _podcastindex_headers()


class TestFetchEpisodes(unittest.TestCase):
    @patch("podcast_fetch._api_get")
    def test_returns_episodes_with_audio(self, mock_api):
        mock_api.return_value = {
            "items": [
                {
                    "id": 12345,
                    "title": "Episode One",
                    "enclosureUrl": "https://example.com/ep1.mp3",
                    "datePublished": 1700000000,
                    "link": "https://example.com/ep1",
                    "duration": 3600,
                },
                {
                    "id": 12346,
                    "title": "Episode Two",
                    "enclosureUrl": "https://example.com/ep2.mp3",
                    "datePublished": 1700100000,
                    "link": "",
                    "duration": 1800,
                },
            ]
        }
        episodes = fetch_episodes("6958769")
        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes[0]["episode_id"], "12345")
        self.assertEqual(episodes[0]["audio_url"], "https://example.com/ep1.mp3")

    @patch("podcast_fetch._api_get")
    def test_skips_episodes_without_audio(self, mock_api):
        mock_api.return_value = {
            "items": [
                {"id": 1, "title": "No Audio", "enclosureUrl": ""},
                {
                    "id": 2,
                    "title": "Has Audio",
                    "enclosureUrl": "https://example.com/ep.mp3",
                },
            ]
        }
        episodes = fetch_episodes("123")
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["title"], "Has Audio")

    @patch("podcast_fetch._api_get")
    def test_returns_empty_on_api_error(self, mock_api):
        mock_api.side_effect = urllib.error.URLError("timeout")
        episodes = fetch_episodes("123")
        self.assertEqual(episodes, [])


class TestFetchNewEpisodes(unittest.TestCase):
    @patch("podcast_fetch.fetch_episodes")
    def test_limits_to_max_per_podcast(self, mock_fetch):
        mock_fetch.return_value = [
            {"episode_id": str(i), "title": f"Ep {i}", "audio_url": f"http://x/{i}.mp3",
             "published": "", "episode_url": "", "duration": 0}
            for i in range(10)
        ]
        podcasts = [{"name": "Test Pod", "podcast_id": "123"}]
        results = fetch_new_episodes(podcasts)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["podcast_name"], "Test Pod")

    @patch("podcast_fetch.fetch_episodes")
    def test_skips_podcast_with_no_episodes(self, mock_fetch):
        mock_fetch.return_value = []
        podcasts = [{"name": "Empty", "podcast_id": "999"}]
        results = fetch_new_episodes(podcasts)
        self.assertEqual(results, [])
