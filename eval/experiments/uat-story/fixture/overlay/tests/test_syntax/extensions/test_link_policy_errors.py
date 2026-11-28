"""
Python Markdown

A Python implementation of John Gruber's Markdown.

Documentation: https://python-markdown.github.io/
License: BSD (see LICENSE.md for details).
"""

import unittest

from markdown.extensions.linkpolicy import LinkPolicyError


class TestLinkPolicyError(unittest.TestCase):

    def test_the_error_is_a_value_error(self):
        self.assertTrue(issubclass(LinkPolicyError, ValueError))

    def test_the_error_takes_a_message_like_any_value_error(self):
        """ Applications raise LinkPolicyError with their own message, as they would a ValueError. """
        error = LinkPolicyError('comment 12: a link was blocked')
        self.assertEqual(str(error), 'comment 12: a link was blocked')
        self.assertEqual(error.args, ('comment 12: a link was blocked',))
