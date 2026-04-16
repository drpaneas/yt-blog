import unittest

from autopublish import _extract_video_id


class TestExtractVideoId(unittest.TestCase):
    def test_standard_watch_url(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )

    def test_watch_url_with_extra_params(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/watch?v=abc123&t=120"),
            "abc123",
        )

    def test_watch_url_trailing_slash(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/watch/?v=abc123"),
            "abc123",
        )

    def test_mobile_url(self):
        self.assertEqual(
            _extract_video_id("https://m.youtube.com/watch?v=abc123"),
            "abc123",
        )

    def test_short_url(self):
        self.assertEqual(
            _extract_video_id("https://youtu.be/abc123"),
            "abc123",
        )

    def test_short_url_with_params(self):
        self.assertEqual(
            _extract_video_id("https://youtu.be/abc123?t=60"),
            "abc123",
        )

    def test_shorts_url(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/shorts/abc123"),
            "abc123",
        )

    def test_live_url(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/live/abc123"),
            "abc123",
        )

    def test_embed_url(self):
        self.assertEqual(
            _extract_video_id("https://www.youtube.com/embed/abc123"),
            "abc123",
        )

    def test_non_youtube_url(self):
        self.assertIsNone(_extract_video_id("https://vimeo.com/12345"))

    def test_youtube_channel_url(self):
        self.assertIsNone(
            _extract_video_id("https://www.youtube.com/@SomeChannel")
        )

    def test_empty_string(self):
        self.assertIsNone(_extract_video_id(""))

    def test_no_v_param(self):
        self.assertIsNone(
            _extract_video_id("https://www.youtube.com/watch?list=PLxyz")
        )
