import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from autopublish import run

SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <entry>
    <yt:videoId>integrationVID</yt:videoId>
    <title>How AI Agents Work</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=integrationVID"/>
    <published>2026-04-15T10:00:00+00:00</published>
  </entry>
</feed>"""


class TestAutopublishDryRun(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.blog_repo = self.tmp / "blog"
        self.blog_repo.mkdir()
        (self.blog_repo / "content" / "post").mkdir(parents=True)
        self.wiki_dir = self.tmp / "wiki"
        self.wiki_dir.mkdir()
        (self.wiki_dir / "raw").mkdir()
        self.yt_dir = self.tmp / "youtube"
        self.yt_dir.mkdir()

        self.state_dir = self.tmp / "state"
        self.state_dir.mkdir()

        config_text = f"""
state_dir = "{self.state_dir}"

[paths]
blog_repo = "{self.blog_repo}"
llmwiki_dir = "{self.wiki_dir}"
youtube_repo_dir = "{self.yt_dir}"

[[channel]]
name = "Test Channel"
channel_id = "UCtest123"
"""
        self.config_path = self.tmp / "channels.toml"
        self.config_path.write_text(config_text)

    def tearDown(self):
        self.tmpdir.cleanup()

    @patch("feed_checker.urllib.request.urlopen")
    def test_dry_run_does_not_modify_state(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = SAMPLE_ATOM.encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = run(self.config_path, dry_run=True)

        self.assertEqual(result, 0)
        state_file = self.state_dir / "seen_videos.json"
        self.assertFalse(state_file.exists())
