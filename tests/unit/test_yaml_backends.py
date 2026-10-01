"""AEW reads and writes YAML through libyaml when PyYAML has it (M3 step 7, m3-performance.md), and that choice
changes no value read and no byte written: the pure-Python and libyaml paths agree on AEW's own documents and on
strings chosen to stress quoting, folding and type resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aew import util

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted([*ROOT.glob("src/aew/**/*.yaml"), *ROOT.glob("tests/fixtures/**/*.yaml"), *ROOT.glob(".aew/**/*.yaml")])
STRINGS = ["", " leading", "trailing ", "a: b", "- x", "#c", "multi\nline", "multi\nline\n", "tab\there", "ünïcødé →",
           "x" * 250, "long words " * 40, "'quote'", '"dq"', "null", "yes", "0123", "1e3", "2026-09-27T23:16:18Z",
           "@at", "`bt`", "a b", "\x07bell", "aew1.tk_0000000000000000.redacted"]


class _PythonDumper(yaml.SafeDumper):
    pass


_PythonDumper.add_representer(str, util._str_representer)


def python_dump(data):
    return yaml.dump(data, Dumper=_PythonDumper, sort_keys=False, allow_unicode=True, default_flow_style=False,
                     width=100)


def typed(x):
    if isinstance(x, dict):
        return {typed(k): typed(v) for k, v in x.items()}
    if isinstance(x, list):
        return [typed(v) for v in x]
    return (type(x).__name__, x)


def test_libyaml_is_used_where_pyyaml_has_it():
    if yaml.__with_libyaml__:
        assert util._SafeLoader is yaml.CSafeLoader and issubclass(util._Dumper, yaml.CSafeDumper)
    else:
        assert util._SafeLoader is yaml.SafeLoader and issubclass(util._Dumper, yaml.SafeDumper)


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_documents_read_and_write_identically(path):
    text = path.read_text(encoding="utf-8")
    data = util.load_yaml(text)
    assert typed(data) == typed(yaml.load(text, Loader=yaml.SafeLoader))
    assert util.dump_yaml(data) == python_dump(data)


def test_strings_read_and_write_identically():
    data = {"k": STRINGS, **{f"s{i}": s for i, s in enumerate(STRINGS)}, "nested": [{"a": s} for s in STRINGS]}
    written = util.dump_yaml(data)
    assert written == python_dump(data)
    assert typed(util.load_yaml(written)) == typed(data)
