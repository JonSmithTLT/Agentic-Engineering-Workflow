"""In-memory commits for the project-map tests (register F22.1): a ``TrackedTree`` over a dict of blobs, with Git's
own blob ids, so the generator can be tested without git."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aew.maps.canonical import Entry, render_bytes
from aew.maps.gitobjects import TrackedTree

COMMIT, TREE = "c" * 40, "e" * 40
LFS = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 12\n"


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 - Git's object id, not security


def tree_of(files: dict[str, Any], *, missing: frozenset[str] = frozenset()) -> TrackedTree:
    """An in-memory commit: ``path -> bytes`` (a regular file), ``("link", target)``, ``("gitlink", oid)`` or
    ``("raw", name_bytes, data)`` for a name that is not valid UTF-8."""
    entries, blobs = [], {}
    for path, spec in files.items():
        if isinstance(spec, bytes):
            oid = blob_id(spec)
            entries.append(Entry("100644", "blob", oid, len(spec), path))
            if path not in missing:
                blobs[oid] = spec
        elif spec[0] == "link":
            oid = blob_id(spec[1])
            entries.append(Entry("120000", "blob", oid, len(spec[1]), path))
            blobs[oid] = spec[1]
        elif spec[0] == "gitlink":
            entries.append(Entry("160000", "commit", spec[1], None, path))
        else:
            name, utf8 = render_bytes(spec[1])
            oid = blob_id(spec[2])
            entries.append(Entry("100644", "blob", oid, len(spec[2]), name, utf8))
            blobs[oid] = spec[2]
    return TrackedTree(commit=COMMIT, tree=TREE, object_format="sha1", entries=entries, fetch=blobs.get)


PYPROJECT = b'[project]\nname = "demo"\n[project.scripts]\ndemo = "demo.cli:main"\n[tool.pytest.ini_options]\n' \
            b'addopts = "-q"\n[tool.pyright]\n'
PACKAGE_JSON = json.dumps({"name": "web", "bin": {"webctl": "bin/ctl.js"}, "main": "index.js",
                           "scripts": {"test": "jest"}}).encode()
SAMPLE: dict[str, Any] = {
    "README.md": b"# demo\n",
    "pyproject.toml": PYPROJECT,
    ".gitattributes": b"gen/** linguist-generated\nthird/** linguist-vendored=true\n*.txt text\n",
    "src/demo/__init__.py": b"",
    "src/demo/__main__.py": b"print('x')\n",
    "src/demo/cli.py": b"def main(): ...\n",
    "tests/test_cli.py": b"def test(): ...\n",
    "tests/conftest.py": b"",
    "ui/package.json": PACKAGE_JSON,
    "ui/index.js": b"",
    "ui/node_modules/left/index.js": b"",
    "ui/.gitattributes": b"dist/** linguist-generated\n",
    "deep/a/b/c/d/e.go": b"package e\n",
    "deep/Cargo.toml": b'[package]\nname = "x"\n[[bin]]\nname = "tool"\npath = "src/tool.rs"\n',
    "native/compile_commands.json": b"[]",
    "assets/logo.xyz": b"\x00\x01",
    "proto/api_pb2.py": b"",
    "vendor/lib.c": b"int x;\n",
    "sub/module": ("gitlink", "a" * 40),
    "link.toml": ("link", b"../../outside/pyproject.toml"),
}
