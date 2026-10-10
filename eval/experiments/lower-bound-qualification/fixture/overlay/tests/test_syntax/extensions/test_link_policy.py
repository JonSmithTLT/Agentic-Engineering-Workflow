"""
Python Markdown

A Python implementation of John Gruber's Markdown.

Documentation: https://python-markdown.github.io/
License: BSD (see LICENSE.md for details).
"""

from markdown.test_tools import TestCase
from markdown.extensions.linkpolicy import LinkPolicyError

from .linkpolicy_support import PolicyTestMixin


class TestLinkPolicy(PolicyTestMixin, TestCase):

    def test_javascript_link_is_blocked(self):
        self.assertBlocked('[x](javascript:alert)', 'javascript:alert')

    def test_data_link_is_blocked(self):
        self.assertBlocked('[x](data:text/html,hello)', 'data:text/html,hello')

    def test_https_link_is_kept(self):
        self.assertMarkdownRenders(
            '[home](https://example.com/)',
            '<p><a href="https://example.com/">home</a></p>',
            extensions=[self.policy(internal_hosts=['example.com'])]
        )

    def test_blocked_link_keeps_its_text(self):
        self.assertMarkdownRenders(
            '[click me](javascript:alert)',
            '<p><a data-link-policy="blocked">click me</a></p>',
            extensions=[self.policy()]
        )

    def test_relative_link_is_kept_by_default(self):
        self.assertKept('[docs](../docs/)', '../docs/')

    def test_relative_link_can_be_blocked(self):
        self.assertBlocked('[docs](../docs/)', '../docs/', allow_relative=False)

    def test_blocked_schemes_as_a_string(self):
        self.assertBlocked('[x](ftp://example.com/)', 'ftp://example.com/', blocked_schemes='ftp, javascript')

    def test_strict_mode_raises(self):
        html = None
        with self.assertRaises(LinkPolicyError):
            html, _ = self.render('[x](javascript:alert)', strict=True)
        self.assertIsNone(html)
