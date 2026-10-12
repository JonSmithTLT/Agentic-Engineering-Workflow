"""The pack-truth provenance hook's own guarantees (the pack-truth plan, reviewed CLEAR, §2.1-§2.3), without rendering:
the hook functions and their kinds, what the hook wraps, the marker form and its parser, and the patched measures."""

from __future__ import annotations

import argparse
import ast
import collections
import types

import pt_hook
import pytest

U0, U1, U2, V0, V1, V2 = "", "", "", "", "", ""


def test_hook_functions_have_allowed_kinds():
    """§2.1 (V11-1), the allowed-kind test: the hook functions are the renderers (22), the producers dispositioned
    worker text (18) or fenced (3), the manual-delivery methods (2), the parser builders (23) and the worker result
    methods (3): 71 in 22 modules, each defined in its module exactly once. Any other kind fails."""
    kinds = collections.Counter(pt_hook.HOOK_FUNCTIONS.values())
    assert set(kinds) <= pt_hook.ALLOWED_KINDS
    assert kinds == {"renderer": 22, "producer:worker text": 18, "producer:fenced": 3, "manual-delivery": 2,
                     "parser-builder": 23, "result-method": 3}
    modules = pt_hook.hook_modules()
    assert (len(pt_hook.HOOK_FUNCTIONS), len(modules)) == (71, 22)
    for rel, quals in modules.items():
        defs = pt_hook.qualnames(ast.parse((pt_hook.PKG / rel).read_text(encoding="utf-8")))
        assert set(quals) <= set(defs), rel


def test_a_hook_function_of_another_kind_fails_the_allowed_kind_test(monkeypatch):
    monkeypatch.setitem(pt_hook.HOOK_FUNCTIONS, ("engine/outbox.py", "record_path"), "producer:not worker text")
    assert set(pt_hook.HOOK_FUNCTIONS.values()) - pt_hook.ALLOWED_KINDS == {"producer:not worker text"}


def test_hook_wraps_output_positions_with_a_space_only():
    """§2.2 (V11-1): inside the 71 hook functions the hook classifies every string constant exactly as the plan's
    table counts them (per function, as the scan counts), and wraps only the output-position constants that contain a
    space; a semantic, dict-key, docstring, raise or log constant is never wrapped."""
    totals: collections.Counter[str] = collections.Counter()
    for rel in pt_hook.hook_modules():
        source = (pt_hook.PKG / rel).read_text(encoding="utf-8")
        tree, plan = pt_hook.plan_module(rel, source, registry=pt_hook.Registry())
        totals.update(plan.counts)
        defs = pt_hook.qualnames(tree)
        classes = {}
        for q in pt_hook.hook_modules()[rel]:
            classes.update(pt_hook.positions(defs[q]))
        constants = {plan.keys[id(n)]: n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                     and isinstance(n.value, str)}
        assert all(classes[p] == "output" and " " in constants[p] for p in plan.wrapped), rel
        assert {p for p, c in classes.items() if c == "output"} == set(plan.wrapped), rel
    assert totals == {"output": 583, "output-spaceless": 315, "semantic": 509, "dict-key": 177, "other": 686,
                      "docstring": 26, "raise": 40}


def test_every_string_constant_has_its_own_key():
    """The hook keys nodes by position, and Python before 3.12 places an f-string's parts at the f-string's own
    position: the keys still name one constant each (``pt_hook.node_keys``), here and on 3.11."""
    for rel in pt_hook.hook_modules():
        tree = ast.parse((pt_hook.PKG / rel).read_text(encoding="utf-8"))
        keys = pt_hook.node_keys(tree)
        constants = [keys[id(n)] for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        assert len(constants) == len(set(constants)), rel
    js = ast.parse('f"a {b} c{d!r:>{w}} e"').body[0].value  # type: ignore[attr-defined]
    keys = pt_hook.node_keys(js)
    parts = [keys[id(v)] for v in js.values]
    assert [p[-2:] for p in parts] == [("part", i) for i in range(5)]
    spec = js.values[3].format_spec
    assert keys[id(spec)] == (*parts[3], "spec") and keys[id(spec.values[1])] == (*parts[3], "spec", "part", 1)


def test_semantic_positions_are_never_output():
    """§2.2, the classification test: a constant used as a subscript key, a comparand or a lookup method's first
    argument inside a hook function is classed semantic (or a docstring, raise or log), never output."""
    missing = []
    for rel, quals in pt_hook.hook_modules().items():
        defs = pt_hook.qualnames(ast.parse((pt_hook.PKG / rel).read_text(encoding="utf-8")))
        for q in quals:
            pos = pt_hook.positions(defs[q])
            for n in ast.walk(defs[q]):
                cands = [n.slice] if isinstance(n, ast.Subscript) else [n.left, *n.comparators] \
                    if isinstance(n, ast.Compare) else n.args[:1] if isinstance(n, ast.Call) and \
                    isinstance(n.func, ast.Attribute) and n.func.attr in pt_hook.LOOKUP else []
                for x in cands:
                    missing += [(rel, p) for p in pt_hook._strings(x)
                                if pos.get(p) not in ("semantic", "docstring", "raise", "log")]
    assert missing == []


def test_marker_form_is_text_before_id_and_strips_exactly():
    """§2.2: `U+E000 text U+E001 id U+E002`; the id comes after the text, so two wrapped texts order by their text."""
    a, b = pt_hook.wrap_unit("alpha", "u9"), pt_hook.wrap_unit("beta", "u1")
    assert a == f"{U0}alpha{U1}u9{U2}" and sorted([b, a]) == [a, b]
    assert pt_hook.strip(f"x {a} y {pt_hook.wrap_value('v', 'v3')}") == "x alpha y v"


def test_nested_markers_innermost():
    """§2.2: a value marker can hold unit markers (a joined list of wrapped data); the innermost decides a span's
    source, and a span across a child marker's boundary has none."""
    joined = "; ".join([pt_hook.wrap_unit("run the checks", "u1"), pt_hook.wrap_unit("submit evidence", "u2")])
    text = "- authority: " + pt_hook.wrap_value(joined, "v7")
    stripped, roots = pt_hook.parse(text)
    s = stripped.index("submit")
    m, why = pt_hook.span_source(roots, s, s + len("submit"))
    assert (m.kind, m.ident, why) == ("unit", "u2", "")
    assert [x.ident for x in pt_hook.chain(m)] == ["u2", "v7"]
    sep = stripped.index("; ")
    assert pt_hook.span_source(roots, sep, sep + 1)[0].ident == "v7"  # the separator belongs to the join's value
    assert pt_hook.span_source(roots, s - 4, s + 3) == (None, "straddles")
    assert pt_hook.span_source(roots, 0, 1) == (None, "unmarked")


@pytest.mark.parametrize("text", [
    f"{U0}open never closed", f"closed {U1}u1{U2}", f"{U0}a{U1}u1{V2}", f"{U0}a{V1}v1{V2}", f"{U0}a{U1}u1",
    f"stray {U2}", f"{V0}value{U1}u1{U2}",
])
def test_unbalanced_marker_fails(text):
    """v9: an unbalanced, unterminated or mismatched marker fails closed."""
    with pytest.raises(pt_hook.UnbalancedMarkers):
        pt_hook.parse(text)


@pytest.mark.parametrize("width", [40, 60, 80, 100, 140, 220])
def test_help_wrapping_measures_stripped_text(width):
    """§2.2 (V12-1): argparse wraps marked help exactly where it wraps the stripped help, and the markers survive the
    wrap, balanced, possibly across a line break."""
    plain = ("show this help text, which is long enough to wrap at every width the help trace uses, with "
             "hyphenated-words-that-break and a path/like/this one, then more words to fill the line out")
    marked = (pt_hook.wrap_unit(plain[:70], "u1") + "  " + pt_hook.wrap_value(plain[70:121], "v2") + " "
              + pt_hook.wrap_unit(plain[121:].strip(), "u3"))
    fmt = argparse.HelpFormatter("aew")
    original = argparse.HelpFormatter._split_lines
    patched = pt_hook._split_lines_stripped(original)
    want = original(fmt, pt_hook.strip(marked), width)
    got = patched(fmt, marked, width)
    assert [pt_hook.strip(line) for line in got] == want
    pt_hook.parse("\n".join(got))  # balanced across the breaks
    fill = pt_hook._fill_text_stripped(argparse.HelpFormatter._fill_text)
    assert pt_hook.strip(fill(fmt, marked, width, "  ")) == argparse.HelpFormatter._fill_text(
        fmt, pt_hook.strip(marked), width, "  ")


def test_hashing_and_size_measure_stripped_text():
    """§2.2 (V10-2): under the hook the hashing helpers and the pack budget's size measure the stripped text."""
    import hashlib

    util = types.SimpleNamespace(sha256_bytes=lambda b: hashlib.sha256(b).hexdigest())
    pt_hook._patch_util(util)
    marked = pt_hook.wrap_unit("the pack text", "u4")
    assert util.sha256_bytes(marked.encode("utf-8")) == hashlib.sha256(b"the pack text").hexdigest()
    ctx = types.SimpleNamespace()
    pt_hook._patch_context(ctx)
    assert ctx._size([marked, "x"]) == len("the pack text") + 1 + 2


def test_a_data_value_keeps_its_surrounding_whitespace_outside_the_marker():
    """A renderer's `.strip()` of a fenced or YAML value must strip what it stripped unhooked (found by the
    strip-equivalence check: a plan's trailing newline stayed inside the marker)."""
    fenced = pt_hook.fence("1. Add subtract.\n", "plan_text", pt_hook.Registry())
    assert fenced.strip() != fenced and pt_hook.strip(fenced.strip()) == "1. Add subtract."
    assert pt_hook.fence("\n", "record_body", pt_hook.Registry()) == "\n"


def test_install_refuses_after_aew_is_imported(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "aew.fake_loaded", types.ModuleType("aew.fake_loaded"))
    with pytest.raises(pt_hook.HookError):
        pt_hook.install()
