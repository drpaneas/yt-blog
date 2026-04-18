import unittest

from publish_utils import slugify


class TestSlugify(unittest.TestCase):
    def test_simple_name(self):
        self.assertEqual(slugify("My Channel"), "my-channel")

    def test_special_characters(self):
        self.assertEqual(slugify("Tech @ Home!"), "tech-home")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "unknown")

    def test_unicode_only(self):
        self.assertEqual(slugify("日本語"), "unknown")

    def test_already_slugified(self):
        self.assertEqual(slugify("my-channel"), "my-channel")

    def test_extra_whitespace(self):
        self.assertEqual(slugify("  lots   of   spaces  "), "lots-of-spaces")
