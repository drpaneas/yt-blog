import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hugo_formatter import add_hugo_front_matter


class TestHugoFormatter(unittest.TestCase):
    def setUp(self):
        self.tmpdir = TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_prepends_front_matter_and_removes_h1(self):
        md = "# My Great Title\n\nSome content here.\n"
        path = self.tmp / "test.md"
        path.write_text(md)
        add_hugo_front_matter(path)
        result = path.read_text()
        self.assertTrue(result.startswith("+++\n"))
        self.assertIn('title = "My Great Title"', result)
        self.assertIn('categories = ["youtube"]', result)
        self.assertIn('tags = ["ai", "youtube"]', result)
        self.assertIn("date = ", result)
        self.assertIn("+++\n", result)
        self.assertNotIn("# My Great Title", result)
        self.assertIn("Some content here.", result)

    def test_custom_categories_and_tags(self):
        md = "# Custom Title\n\nBody.\n"
        path = self.tmp / "test.md"
        path.write_text(md)
        add_hugo_front_matter(path, categories=["tech"], tags=["ml", "deep-learning"])
        result = path.read_text()
        self.assertIn('categories = ["tech"]', result)
        self.assertIn('tags = ["ml", "deep-learning"]', result)

    def test_no_h1_uses_filename(self):
        md = "Some content without a title.\n"
        path = self.tmp / "youtube-blog-fallback-vid123.md"
        path.write_text(md)
        add_hugo_front_matter(path)
        result = path.read_text()
        self.assertIn('title = "youtube-blog-fallback-vid123"', result)

    def test_h1_with_special_chars(self):
        md = '# Title With "Quotes" & Stuff\n\nBody.\n'
        path = self.tmp / "test.md"
        path.write_text(md)
        add_hugo_front_matter(path)
        result = path.read_text()
        self.assertIn("title = ", result)
        self.assertTrue(result.startswith("+++\n"))

    def test_preserves_body_content(self):
        md = "# Title\n\n## Section 1\n\nParagraph one.\n\n## Section 2\n\nParagraph two.\n"
        path = self.tmp / "test.md"
        path.write_text(md)
        add_hugo_front_matter(path)
        result = path.read_text()
        self.assertIn("## Section 1", result)
        self.assertIn("Paragraph one.", result)
        self.assertIn("## Section 2", result)
        self.assertIn("Paragraph two.", result)

    def test_strips_leading_blank_lines_after_h1_removal(self):
        md = "# Title\n\n\n\nBody starts here.\n"
        path = self.tmp / "test.md"
        path.write_text(md)
        add_hugo_front_matter(path)
        result = path.read_text()
        parts = result.split("+++\n")
        body = parts[2]
        self.assertFalse(body.startswith("\n\n\n"))
