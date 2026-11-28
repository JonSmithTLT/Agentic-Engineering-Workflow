"""
Render a user comment for the comments site, and list the links it leads off the site.

The site shows a comment's outbound links beside it ("Links in this comment"). Both come from one render, under the
link policy the site uses for every comment.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from markdown import Markdown
from markdown.extensions.linkpolicy import LinkPolicyExtension

SITE_HOSTS = ['comments.example']
LINK = re.compile(r'<a href="([^"]*)">')


def render(text: str) -> str:
    """ A comment's HTML, under the site's link policy. """
    return Markdown(extensions=[LinkPolicyExtension(internal_hosts=SITE_HOSTS)]).convert(text)


def outbound_links(html: str) -> list[str]:
    """ The URLs of the links in a rendered comment that leave the site, in order. Blocked links have no URL. """
    out = []
    for url in LINK.findall(html):
        parts = urlsplit(url)
        if parts.scheme in ('http', 'https', '') and parts.netloc and parts.hostname not in SITE_HOSTS:
            out.append(url)
    return out
