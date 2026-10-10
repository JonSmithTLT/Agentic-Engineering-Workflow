"""
Python Markdown

A Python implementation of John Gruber's Markdown.

Documentation: https://python-markdown.github.io/
License: BSD (see LICENSE.md for details).
"""

from markdown.test_tools import TestCase


class TestWikiLinkSpaces(TestCase):

    def test_spaces_in_a_label_become_hyphens(self):
        self.assertMarkdownRenders(
            '[[Two Words]]',
            '<p><a class="wikilink" href="/Two-Words/">Two Words</a></p>',
            extensions=['wikilinks']
        )
