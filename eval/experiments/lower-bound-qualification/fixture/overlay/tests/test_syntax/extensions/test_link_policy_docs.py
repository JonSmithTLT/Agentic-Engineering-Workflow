"""
Python Markdown

A Python implementation of John Gruber's Markdown.

Documentation: https://python-markdown.github.io/
License: BSD (see LICENSE.md for details).
"""

import os
import unittest

from markdown.extensions.linkpolicy import schema

DOC = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'docs', 'extensions', 'link_policy.md')


class TestLinkPolicyDocs(unittest.TestCase):

    def test_every_option_is_documented(self):
        with open(DOC, encoding='utf-8') as f:
            text = f.read()
        for name in schema.DEFAULTS:
            self.assertIn('`{}`'.format(name), text, 'option {} is not in docs/extensions/link_policy.md'.format(name))
