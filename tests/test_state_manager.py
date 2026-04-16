import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from state_manager import StateManager


class TestStateManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.state_dir = Path(self.tmpdir.name)
        self.manager = StateManager(self.state_dir)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_empty_state(self):
        state = self.manager.load()
        self.assertEqual(state, {})

    def test_save_and_load_roundtrip(self):
        self.manager.mark_seen("abc123", {
            "title": "Test Video",
            "filename": "youtube-blog-test-abc123.md",
            "channel": "Test Channel",
            "published": True,
        })
        state = self.manager.load()
        self.assertIn("abc123", state)
        self.assertEqual(state["abc123"]["title"], "Test Video")
        self.assertTrue(state["abc123"]["published"])
        self.assertIn("processed_at", state["abc123"])

    def test_is_seen(self):
        self.assertFalse(self.manager.is_seen("abc123"))
        self.manager.mark_seen("abc123", {
            "title": "Test",
            "filename": "test.md",
            "channel": "Ch",
            "published": False,
        })
        self.assertTrue(self.manager.is_seen("abc123"))

    def test_atomic_write_survives_concurrent_reads(self):
        self.manager.mark_seen("vid1", {
            "title": "First",
            "filename": "first.md",
            "channel": "Ch",
            "published": True,
        })
        state_file = self.state_dir / "seen_videos.json"
        raw = json.loads(state_file.read_text())
        self.assertIn("vid1", raw)

    def test_load_corrupted_file_raises(self):
        state_file = self.state_dir / "seen_videos.json"
        state_file.write_text("not json{{{")
        with self.assertRaises(json.JSONDecodeError):
            self.manager.load()
