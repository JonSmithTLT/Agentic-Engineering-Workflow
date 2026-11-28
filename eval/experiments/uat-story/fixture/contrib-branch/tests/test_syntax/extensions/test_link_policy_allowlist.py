"""
Python Markdown

A Python implementation of John Gruber's Markdown.

Documentation: https://python-markdown.github.io/
License: BSD (see LICENSE.md for details).
"""

from markdown.test_tools import TestCase

from .linkpolicy_support import PolicyTestMixin


class TestLinkPolicyAllowList(PolicyTestMixin, TestCase):

    policy_options = {'allowed_schemes': ['https', 'mailto']}

    def test_an_allowed_scheme_is_kept(self):
        self.assertKept('[home](https://example.com/)', 'https://example.com/')

    def test_mailto_is_kept(self):
        self.assertKept('[mail](mailto:me@example.com)', 'mailto:me@example.com')

    def test_a_scheme_not_listed_is_blocked(self):
        self.assertBlocked('[x](ftp://example.com/)', 'ftp://example.com/')

    def test_javascript_is_blocked(self):
        self.assertBlocked('[x](javascript:alert)', 'javascript:alert')

    def test_relative_links_follow_allow_relative(self):
        self.assertKept('[docs](../docs/)', '../docs/')

    def test_off_by_default(self):
        self.assertKept('[x](ftp://example.com/)', 'ftp://example.com/', allowed_schemes=[])
