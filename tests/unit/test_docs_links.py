"""Every relative link in the repository's own Markdown resolves, so moving a document cannot silently break a link.

Covers the root README, `docs/` (except the frozen specification set, which may not change) and `eval/`. `web/`
keeps its own documents and is out of scope. Link fragments (`#section`) are not checked; the file must exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
FROZEN = {d["path"] for d in yaml.safe_load((ROOT / "docs" / "spec-pin.yaml").read_text(encoding="utf-8"))["documents"]}
LINK = re.compile(r"\]\(([^)\s]+)\)")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)  # links inside code are examples, not links


def documents() -> list[Path]:
    found = [ROOT / "README.md", *(ROOT / "docs").rglob("*.md"), *(ROOT / "eval").rglob("*.md")]
    return sorted(p for p in found if p.relative_to(ROOT).as_posix() not in FROZEN)


def broken_links(doc: Path) -> list[str]:
    text = CODE.sub("", doc.read_text(encoding="utf-8"))
    broken = []
    for target in LINK.findall(text):
        path = target.split("#", 1)[0]
        if not path or re.match(r"^[a-z][a-z0-9+.-]*:", path) or path.startswith("/"):
            continue
        if not (doc.parent / path).exists():
            broken.append(target)
    return broken


@pytest.mark.parametrize("doc", documents(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_relative_link_resolves(doc):
    assert broken_links(doc) == []


def test_the_docs_map_lists_every_document():
    """docs/README.md is the map: every document under docs/ (outside skills/, which has its own README) is on it."""
    readme = ROOT / "docs" / "README.md"
    listed = {(readme.parent / t.split("#", 1)[0]).resolve() for t in LINK.findall(readme.read_text(encoding="utf-8"))}
    docs = [p for p in (ROOT / "docs").rglob("*") if p.is_file() and p.suffix in (".md", ".yaml")
            and "skills" not in p.relative_to(ROOT / "docs").parts and p != readme]
    missing = sorted(p.relative_to(ROOT).as_posix() for p in docs if p.resolve() not in listed)
    assert missing == [], "add these to docs/README.md: " + ", ".join(missing)
