import json
import unittest
from unittest.mock import patch, MagicMock
from feed_checker import parse_atom_feed, fetch_new_videos, _fetch_via_rss, _fetch_via_ytdlp

SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <entry>
    <yt:videoId>abc123</yt:videoId>
    <title>First AI Video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
    <published>2026-04-15T10:00:00+00:00</published>
  </entry>
  <entry>
    <yt:videoId>def456</yt:videoId>
    <title>Second Video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=def456"/>
    <published>2026-04-14T10:00:00+00:00</published>
  </entry>
</feed>"""


class TestParseAtomFeed(unittest.TestCase):
    def test_parse_two_entries(self):
        entries = parse_atom_feed(SAMPLE_ATOM)
        self.assertEqual(len(entries), 2)

    def test_entry_fields(self):
        entries = parse_atom_feed(SAMPLE_ATOM)
        first = entries[0]
        self.assertEqual(first["video_id"], "abc123")
        self.assertEqual(first["title"], "First AI Video")
        self.assertEqual(first["url"], "https://www.youtube.com/watch?v=abc123")
        self.assertEqual(first["published"], "2026-04-15T10:00:00+00:00")

    def test_empty_feed(self):
        empty = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Empty</title>
</feed>"""
        entries = parse_atom_feed(empty)
        self.assertEqual(entries, [])

    def test_malformed_xml_raises(self):
        with self.assertRaises(Exception):
            parse_atom_feed("not xml at all <<<")


class TestFetchViaRss(unittest.TestCase):
    @patch("feed_checker.urllib.request.urlopen")
    def test_returns_entries_on_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = SAMPLE_ATOM.encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        entries = _fetch_via_rss("UCtest123")
        self.assertEqual(len(entries), 2)

    @patch("feed_checker.urllib.request.urlopen")
    def test_returns_none_on_network_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Connection refused")
        self.assertIsNone(_fetch_via_rss("UCbroken"))

    @patch("feed_checker.urllib.request.urlopen")
    def test_returns_none_on_error_page(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<title>Error 404 (Not Found)!!1</title>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        self.assertIsNone(_fetch_via_rss("UCbroken"))


class TestFetchViaYtdlp(unittest.TestCase):
    @patch("feed_checker.subprocess.run")
    def test_returns_entries_on_success(self, mock_run):
        lines = "\n".join([
            json.dumps({"id": "vid1", "title": "First", "url": "https://www.youtube.com/watch?v=vid1"}),
            json.dumps({"id": "vid2", "title": "Second", "url": "https://www.youtube.com/watch?v=vid2"}),
        ])
        mock_run.return_value = MagicMock(returncode=0, stdout=lines, stderr="")
        entries = _fetch_via_ytdlp("UCtest")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["video_id"], "vid1")
        self.assertEqual(entries[1]["title"], "Second")

    @patch("feed_checker.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        self.assertIsNone(_fetch_via_ytdlp("UCbroken"))

    @patch("feed_checker.subprocess.run")
    def test_returns_none_when_ytdlp_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError("yt-dlp not found")
        self.assertIsNone(_fetch_via_ytdlp("UCtest"))


class TestFetchNewVideos(unittest.TestCase):
    @patch("feed_checker._fetch_via_ytdlp")
    @patch("feed_checker._fetch_via_rss")
    def test_uses_rss_when_available(self, mock_rss, mock_ytdlp):
        mock_rss.return_value = [
            {"video_id": "abc", "title": "Test", "url": "https://...", "published": ""},
        ]
        channels = [{"name": "Good", "channel_id": "UCgood"}]
        results = fetch_new_videos(channels)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["channel"], "Good")
        mock_ytdlp.assert_not_called()

    @patch("feed_checker._fetch_via_ytdlp")
    @patch("feed_checker._fetch_via_rss")
    def test_falls_back_to_ytdlp_when_rss_fails(self, mock_rss, mock_ytdlp):
        mock_rss.return_value = None
        mock_ytdlp.return_value = [
            {"video_id": "xyz", "title": "Fallback", "url": "https://...", "published": ""},
        ]
        channels = [{"name": "NoRSS", "channel_id": "UCnorss"}]
        results = fetch_new_videos(channels)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Fallback")
        self.assertEqual(results[0]["channel"], "NoRSS")

    @patch("feed_checker._fetch_via_ytdlp")
    @patch("feed_checker._fetch_via_rss")
    def test_skips_channel_when_both_fail(self, mock_rss, mock_ytdlp):
        mock_rss.return_value = None
        mock_ytdlp.return_value = None
        channels = [{"name": "Dead", "channel_id": "UCdead"}]
        results = fetch_new_videos(channels)
        self.assertEqual(results, [])
