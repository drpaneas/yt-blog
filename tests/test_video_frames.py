import tempfile
import unittest
from pathlib import Path

from video_frames import (
    _classify_ocr_text,
    _dhash,
    _hamming_distance,
    _youtube_video_id,
)


class TestYoutubeVideoId(unittest.TestCase):
    def test_standard_watch_url(self):
        self.assertEqual(
            _youtube_video_id("https://www.youtube.com/watch?v=Gv2I7qTux7g"),
            "Gv2I7qTux7g",
        )

    def test_short_url(self):
        self.assertEqual(
            _youtube_video_id("https://youtu.be/Gv2I7qTux7g"),
            "Gv2I7qTux7g",
        )

    def test_shorts_url(self):
        self.assertEqual(
            _youtube_video_id("https://www.youtube.com/shorts/abc123def45"),
            "abc123def45",
        )

    def test_embed_url(self):
        self.assertEqual(
            _youtube_video_id("https://www.youtube.com/embed/Gv2I7qTux7g"),
            "Gv2I7qTux7g",
        )

    def test_url_with_extra_params(self):
        self.assertEqual(
            _youtube_video_id("https://www.youtube.com/watch?v=Gv2I7qTux7g&t=120"),
            "Gv2I7qTux7g",
        )

    def test_invalid_url_returns_none(self):
        self.assertIsNone(_youtube_video_id("https://example.com/video"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_youtube_video_id(""))


class TestDhash(unittest.TestCase):
    def test_identical_images_same_hash(self):
        import numpy as np
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        h1 = _dhash(img)
        h2 = _dhash(img)
        self.assertEqual(h1, h2)

    def test_different_images_different_hash(self):
        import numpy as np
        img1 = np.zeros((100, 100, 3), dtype=np.uint8)
        img1[::2, ::2] = 200
        img2 = np.zeros((100, 100, 3), dtype=np.uint8)
        img2[50:, :] = 255
        h1 = _dhash(img1)
        h2 = _dhash(img2)
        self.assertNotEqual(h1, h2)

    def test_hash_is_integer(self):
        import numpy as np
        img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        self.assertIsInstance(_dhash(img), int)


class TestHammingDistance(unittest.TestCase):
    def test_identical_hashes(self):
        self.assertEqual(_hamming_distance(0b1010, 0b1010), 0)

    def test_completely_different(self):
        self.assertEqual(_hamming_distance(0b0000, 0b1111), 4)

    def test_one_bit_different(self):
        self.assertEqual(_hamming_distance(0b1010, 0b1011), 1)

    def test_symmetric(self):
        self.assertEqual(
            _hamming_distance(0b1100, 0b0011),
            _hamming_distance(0b0011, 0b1100),
        )


class TestClassifyOcrText(unittest.TestCase):
    def test_empty_text_returns_diagram(self):
        self.assertEqual(_classify_ocr_text(""), "diagram")
        self.assertEqual(_classify_ocr_text(None), "diagram")

    def test_short_text_returns_diagram(self):
        self.assertEqual(_classify_ocr_text("hi"), "diagram")

    def test_code_with_brackets(self):
        text = 'fn main() {\n    let x = 42;\n    println!("{}", x);\n}'
        self.assertEqual(_classify_ocr_text(text), "code")

    def test_code_with_keywords(self):
        text = "const std = @import(\"std\");\npub fn main() void {\n    return;\n}"
        self.assertEqual(_classify_ocr_text(text), "code")

    def test_slide_with_bullet_points(self):
        text = "Why Zig?\n- No hidden control flow\n- No hidden allocations\n- Performance is a feature"
        self.assertEqual(_classify_ocr_text(text), "slide")

    def test_natural_language_slide(self):
        text = "The quick brown fox jumps over the lazy dog and this is a presentation slide about animals"
        self.assertEqual(_classify_ocr_text(text), "slide")

    def test_c_code(self):
        text = '#include <stdio.h>\nint main() {\n    printf("hello");\n    return 0;\n}'
        self.assertEqual(_classify_ocr_text(text), "code")

    def test_python_code(self):
        text = "def hello():\n    x = 42\n    if x > 0:\n        return True\n    else:\n        return False"
        self.assertEqual(_classify_ocr_text(text), "code")


class TestFindBlogOutput(unittest.TestCase):
    def test_finds_flat_file(self):
        from autopublish import _find_blog_output
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            flat = repo / "youtube-blog-test-slug-ABC123def45.md"
            flat.write_text("# Test", encoding="utf-8")
            result = _find_blog_output(repo, "ABC123def45")
            self.assertEqual(result, flat)

    def test_finds_page_bundle(self):
        from autopublish import _find_blog_output
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            bundle = repo / "youtube-blog-test-slug-ABC123def45"
            bundle.mkdir()
            index = bundle / "index.md"
            index.write_text("# Test", encoding="utf-8")
            result = _find_blog_output(repo, "ABC123def45")
            self.assertEqual(result, index)

    def test_prefers_newer_file(self):
        import time
        from autopublish import _find_blog_output
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            flat = repo / "youtube-blog-old-ABC123def45.md"
            flat.write_text("# Old", encoding="utf-8")
            time.sleep(0.05)
            bundle = repo / "youtube-blog-new-ABC123def45"
            bundle.mkdir()
            index = bundle / "index.md"
            index.write_text("# New", encoding="utf-8")
            result = _find_blog_output(repo, "ABC123def45")
            self.assertEqual(result, index)

    def test_returns_none_when_no_match(self):
        from autopublish import _find_blog_output
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = _find_blog_output(repo, "NONEXISTENT1")
            self.assertIsNone(result)


class TestFindExistingBlog(unittest.TestCase):
    def test_finds_flat_file(self):
        from autopublish import _find_existing_blog
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            flat = d / "youtube-blog-slug-XYZ789abc12.md"
            flat.write_text("# Test", encoding="utf-8")
            result = _find_existing_blog("XYZ789abc12", d)
            self.assertEqual(result, flat)

    def test_finds_page_bundle(self):
        from autopublish import _find_existing_blog
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            bundle = d / "youtube-blog-slug-XYZ789abc12"
            bundle.mkdir()
            index = bundle / "index.md"
            index.write_text("# Test", encoding="utf-8")
            result = _find_existing_blog("XYZ789abc12", d)
            self.assertEqual(result, index)

    def test_searches_multiple_dirs(self):
        from autopublish import _find_existing_blog
        with tempfile.TemporaryDirectory() as tmp:
            d1 = Path(tmp) / "dir1"
            d2 = Path(tmp) / "dir2"
            d1.mkdir()
            d2.mkdir()
            flat = d2 / "youtube-blog-slug-XYZ789abc12.md"
            flat.write_text("# Test", encoding="utf-8")
            result = _find_existing_blog("XYZ789abc12", d1, d2)
            self.assertEqual(result, flat)

    def test_returns_none_when_no_match(self):
        from autopublish import _find_existing_blog
        with tempfile.TemporaryDirectory() as tmp:
            result = _find_existing_blog("NONEXISTENT1", Path(tmp))
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
