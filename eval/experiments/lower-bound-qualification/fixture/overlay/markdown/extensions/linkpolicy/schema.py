# Python Markdown
# A Python implementation of John Gruber's Markdown.
# Documentation: https://python-markdown.github.io/
# License: BSD (see LICENSE.md for details).
"""
The link policy's options: the one table the extension, its validation and its documentation share.

Each option is `name: [default, description]`, the shape `markdown.extensions.Extension.config` expects.
"""

from __future__ import annotations

import copy
from typing import Any

DEFAULTS: dict[str, list[Any]] = {
    'blocked_schemes': [
        ['javascript', 'vbscript', 'data'],
        'URL schemes whose links are neutralized - Default: javascript, vbscript, data'
    ],
    'allow_relative': [True, 'Keep links without a scheme (relative links) - Default: True'],
    'internal_hosts': [[], "Hosts that are this site's own: links to them are internal - Default: []"],
    'strict': [False, 'Raise LinkPolicyError at a blocked link instead of neutralizing it - Default: False'],
}


def defaults() -> dict[str, list[Any]]:
    """ A fresh copy of the table: `Extension.setConfig` writes into it, so two instances never share one. """
    return copy.deepcopy(DEFAULTS)


def _names(value: Any, option: str) -> list[str]:
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
        raise TypeError(f'{option} is a list of names or a comma-separated string')
    return [v.strip() for v in value if v.strip()]


def validate(configs: dict[str, Any]) -> dict[str, Any]:
    """
    The options as the extension uses them. An unknown option is a `KeyError`, as `Extension.setConfig` raises for
    an option it has no default for.
    """
    unknown = sorted(set(configs) - set(DEFAULTS))
    if unknown:
        raise KeyError(f'unknown link policy option(s): {", ".join(unknown)}')
    return {
        'blocked_schemes': [s.lower() for s in _names(configs['blocked_schemes'], 'blocked_schemes')],
        'allow_relative': bool(configs['allow_relative']),
        'internal_hosts': _names(configs['internal_hosts'], 'internal_hosts'),
        'strict': bool(configs['strict']),
    }
