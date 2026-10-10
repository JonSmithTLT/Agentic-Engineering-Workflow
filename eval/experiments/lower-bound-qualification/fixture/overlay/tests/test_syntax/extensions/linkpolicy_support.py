"""
Python Markdown

A Python implementation of John Gruber's Markdown.

Documentation: https://python-markdown.github.io/
License: BSD (see LICENSE.md for details).

Helpers for the link policy tests: an extension instance with the test's options, a render that keeps the
instance, and an assertion on what the policy blocked.
"""

from markdown import Markdown
from markdown.extensions.linkpolicy import LinkPolicyExtension


class PolicyTestMixin:
    """ Mix into `markdown.test_tools.TestCase`. `policy_options` apply to every test of the class. """

    policy_options = {}

    def policy(self, **options):
        return LinkPolicyExtension(**{**self.policy_options, **options})

    def render(self, source, **options):
        """ The HTML and the extension instance that produced it. """
        extension = self.policy(**options)
        return Markdown(extensions=[extension]).convert(source), extension

    def assertBlocked(self, source, url, **options):
        html, extension = self.render(source, **options)
        self.assertIn('data-link-policy="blocked"', html)
        self.assertNotIn('href="{}"'.format(url), html)
        self.assertIn(url, extension.report())

    def assertKept(self, source, url, **options):
        html, extension = self.render(source, **options)
        self.assertIn('href="{}"'.format(url), html)
        self.assertNotIn(url, extension.report())
