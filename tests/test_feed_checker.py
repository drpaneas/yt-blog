import unittest
from unittest.mock import patch, MagicMock
from feed_checker import parse_atom_feed, fetch_new_videos

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


class TestFetchNewVideos(unittest.TestCase):
    @patch("feed_checker.urllib.request.urlopen")
    def test_fetches_and_parses(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_ATOM.encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        channels = [{"name": "Test", "channel_id": "UCtest123"}]
        results = fetch_new_videos(channels)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["channel"], "Test")
        mock_urlopen.assert_called_once_with(
            "https://www.youtube.com/feeds/videos.xml?channel_id=UCtest123",
            timeout=30,
        )

    @patch("feed_checker.urllib.request.urlopen")
    def test_network_error_skips_channel(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("Connection refused")
        channels = [{"name": "Broken", "channel_id": "UCbroken"}]
        results = fetch_new_videos(channels)
        self.assertEqual(results, [])
