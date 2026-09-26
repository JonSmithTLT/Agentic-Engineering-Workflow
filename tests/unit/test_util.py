from __future__ import annotations

import pytest

from aew.errors import IntegrityError, ValidationFailed
from aew.util import (
    atomic_write,
    create_exclusive,
    dump_yaml,
    glob_match,
    load_yaml,
    parse_frontmatter,
    render_frontmatter,
    sha256_file,
)


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        (".aew/state/control.yaml", ".aew/**", True),
        (".aew", ".aew/**", False),
        ("calc/core.py", "calc/**", True),
        ("calc/sub/x.py", "calc/*.py", False),
        ("calc/x.py", "calc/*.py", True),
        ("a/b/c/gen.h", "**/gen.h", True),
        ("gen.h", "**/gen.h", True),
        ("src/auth/token.py", "src/auth/**", True),
        ("src/authz.py", "src/auth/**", False),
        ("calc\\core.py", "calc/**", True),
    ],
)
def test_glob_match(path, pattern, expected):
    assert glob_match(path, pattern) is expected


def test_frontmatter_round_trip():
    meta = {"id": "T-0001", "title": "Add subtract", "list": [1, 2]}
    body = "## Objective\n\nMulti\nline\n"
    text = render_frontmatter(meta, body)
    got_meta, got_body = parse_frontmatter(text)
    assert got_meta == meta
    assert got_body == body


def test_frontmatter_crlf_tolerated():
    meta, body = parse_frontmatter("---\r\nid: X\r\n---\r\nbody\r\n")
    assert meta == {"id": "X"} and body == "body\n"


def test_frontmatter_missing_rejected():
    with pytest.raises(ValidationFailed):
        parse_frontmatter("no frontmatter here")


def test_yaml_multiline_uses_block_style():
    text = dump_yaml({"note": "a\nb\n"})
    assert "|" in text
    assert load_yaml(text) == {"note": "a\nb\n"}


def test_atomic_write_replaces(tmp_path):
    target = tmp_path / "f.yaml"
    atomic_write(target, "one")
    atomic_write(target, "two")
    assert target.read_text() == "two"
    assert [p.name for p in tmp_path.iterdir()] == ["f.yaml"]  # no temp leftovers


def test_create_exclusive_never_overwrites(tmp_path):
    target = tmp_path / "evidence.md"
    create_exclusive(target, "original")
    with pytest.raises(IntegrityError):
        create_exclusive(target, "forged")
    assert target.read_text() == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["evidence.md"]


def test_sha256_file_missing(tmp_path):
    assert sha256_file(tmp_path / "nope") is None
