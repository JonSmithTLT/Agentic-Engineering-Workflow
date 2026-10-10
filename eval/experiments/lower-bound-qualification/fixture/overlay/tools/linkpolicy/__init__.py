"""
Link checks for the documentation build.

`python -m tools.linkpolicy docs/` lists every link in the documentation sources whose scheme the link policy
does not allow (`schema.py`).
"""

from __future__ import annotations

import os
import re
import sys

from . import rules, schema

LINK = re.compile(r'\]\(([^)\s]+)\)')


def check_tree(root: str) -> list[tuple[str, str, str]]:
    problems = []
    for base, _, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith('.md'):
                continue
            path = os.path.join(base, name)
            with open(path, encoding='utf-8') as f:
                for url in LINK.findall(f.read()):
                    verdict = rules.classify(url, blocked_schemes=schema.DEFAULTS['blocked_schemes'])
                    if not verdict.keep:
                        problems.append((path, url, verdict.reason))
    return problems


def main(argv: list[str]) -> int:
    problems = check_tree(argv[0] if argv else 'docs')
    for path, url, reason in problems:
        print(f'{path}: {url} ({reason})')
    return 1 if problems else 0


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
