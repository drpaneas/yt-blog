import unittest
import unittest.mock
from unittest.mock import patch

from relevance_filter import is_ai_related, _parse_response


class TestParseResponse(unittest.TestCase):
    def test_plain_yes(self):
        self.assertTrue(_parse_response("YES"))

    def test_plain_no(self):
        self.assertFalse(_parse_response("NO"))

    def test_lowercase_yes(self):
        self.assertTrue(_parse_response("yes"))

    def test_yes_with_explanation(self):
        self.assertTrue(_parse_response("Yes, this video is about machine learning."))

    def test_no_with_explanation(self):
        self.assertFalse(_parse_response("No, this is about cooking."))

    def test_whitespace(self):
        self.assertTrue(_parse_response("  yes  \n"))

    def test_empty_response(self):
        self.assertFalse(_parse_response(""))


class TestIsAiRelated(unittest.TestCase):
    @patch("relevance_filter.subprocess.run")
    def test_returns_true_for_yes(self, mock_run):
        mock_run.return_value = unittest.mock.MagicMock(
            returncode=0, stdout="YES\n", stderr=""
        )
        self.assertTrue(is_ai_related("Building LLM Agents"))

    @patch("relevance_filter.subprocess.run")
    def test_returns_false_for_no(self, mock_run):
        mock_run.return_value = unittest.mock.MagicMock(
            returncode=0, stdout="NO\n", stderr=""
        )
        self.assertFalse(is_ai_related("How to bake bread"))

    @patch("relevance_filter.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.side_effect = FileNotFoundError("claude not found")
        result = is_ai_related("Some title")
        self.assertIsNone(result)

    @patch("relevance_filter.subprocess.run")
    def test_returns_none_on_nonzero_exit(self, mock_run):
        mock_run.return_value = unittest.mock.MagicMock(
            returncode=1, stdout="", stderr="error"
        )
        result = is_ai_related("Some title")
        self.assertIsNone(result)
