# Python Markdown
# A Python implementation of John Gruber's Markdown.
# Documentation: https://python-markdown.github.io/
# License: BSD (see LICENSE.md for details).
"""
Link policy: neutralize links whose URL scheme the site does not allow.

    import markdown
    html = markdown.markdown(text, extensions=['markdown.extensions.linkpolicy'])

The options are defined in `schema.DEFAULTS` and documented in `docs/extensions/link_policy.md`. A blocked link
keeps its text, loses its `href` and gets `data-link-policy="blocked"`; in strict mode a blocked link raises
`LinkPolicyError` instead.
"""

from __future__ import annotations

import xml.etree.ElementTree as etree
from typing import TYPE_CHECKING, Any

from .. import Extension
from ...treeprocessors import Treeprocessor
from . import rules, schema

if TYPE_CHECKING:  # pragma: no cover
    from markdown import Markdown


class LinkPolicyError(ValueError):
    """ A link was blocked while the extension runs in strict mode. """


class LinkPolicyTreeprocessor(Treeprocessor):
    """ Check every link once the inline processor has built the `<a>` elements. """

    def __init__(self, md: Markdown, extension: LinkPolicyExtension):
        super().__init__(md)
        self.extension = extension

    def run(self, root: etree.Element) -> None:
        policy = self.extension.policy()
        for el in root.iter('a'):
            href = el.get('href')
            if href is None:
                continue
            verdict = rules.classify(
                href, blocked_schemes=policy['blocked_schemes'], allow_relative=policy['allow_relative']
            )
            if verdict.keep:
                continue
            if policy['strict']:
                raise LinkPolicyError('a link was blocked by the link policy')
            del el.attrib['href']
            el.set('data-link-policy', 'blocked')
            self.extension.blocked.append(href)


class LinkPolicyExtension(Extension):
    """ Add the link policy to a `Markdown` instance. """

    def __init__(self, **kwargs: Any):
        self.config = schema.defaults()
        self.blocked: list[str] = []
        super().__init__(**kwargs)

    def policy(self) -> dict[str, Any]:
        """ The options, checked and normalized. """
        return schema.validate(self.getConfigs())

    def report(self) -> list[str]:
        """ The URLs of the links this extension blocked. """
        return list(self.blocked)

    def extendMarkdown(self, md: Markdown) -> None:
        # TODO(link-policy): mixed-case `JavaScript:` links slip through because this processor runs before the
        # inline processor has built the <a> elements. Register it above the inline processor (priority 25) to fix.
        md.treeprocessors.register(LinkPolicyTreeprocessor(md, self), 'link_policy', 15)


def makeExtension(**kwargs: Any) -> LinkPolicyExtension:  # pragma: no cover
    return LinkPolicyExtension(**kwargs)
