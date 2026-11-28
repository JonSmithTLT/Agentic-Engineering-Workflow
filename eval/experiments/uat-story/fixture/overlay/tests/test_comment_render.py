"""
Python Markdown

A Python implementation of John Gruber's Markdown.

Documentation: https://python-markdown.github.io/
License: BSD (see LICENSE.md for details).

The comments site's renderer (tools/comment_render.py).
"""

import unittest

from tools.comment_render import outbound_links, render


class TestCommentRender(unittest.TestCase):

    def test_outbound_links_are_listed_in_order(self):
        html = render('[a](https://ext.example/a) [b](https://comments.example/b) [c](../c) [d](//other.example/d)')
        self.assertEqual(outbound_links(html), ['https://ext.example/a', '//other.example/d'])

    def test_a_blocked_link_is_not_listed(self):
        html = render('[x](javascript:steal) [y](https://ext.example/y)')
        self.assertEqual(outbound_links(html), ['https://ext.example/y'])

    def test_a_comment_without_links_has_none(self):
        self.assertEqual(outbound_links(render('Just *text*.')), [])
