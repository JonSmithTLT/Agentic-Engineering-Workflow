"""The pack-truth provenance hook's own guarantees (the pack-truth plan, reviewed CLEAR, §2.1-§2.3), without rendering:
the hook functions and their kinds, what the hook wraps, the marker form and its parser, and the patched measures."""

from __future__ import annotations

import argparse
import ast
import collections
import types

import pt_hook
import pt_scan
import pt_trace
import pytest

U0, U1, U2, V0, V1, V2 = (chr(c) for c in range(0xE000, 0xE006))


def test_hook_functions_have_allowed_kinds():
    """§2.1 (V11-1), the allowed-kind test: the hook functions, derived by the render-set scan (item 10 of the
    review), are the renderers (22), the producers dispositioned worker text (18) or fenced (3), the manual-delivery
    methods (2), the parser builders (23) and the worker result methods (3): 71 in 22 modules, each defined in its
    module exactly once. Any other kind fails."""
    hook = pt_hook.hook_functions()
    kinds = collections.Counter(hook.values())
    assert set(kinds) <= pt_hook.ALLOWED_KINDS
    assert kinds == {"renderer": 22, "producer:worker text": 18, "producer:fenced": 3, "manual-delivery": 2,
                     "parser-builder": 23, "result-method": 3}
    modules = pt_hook.hook_modules()
    assert (len(hook), len(modules)) == (71, 22)
    for rel, quals in modules.items():
        defs = pt_hook.qualnames(ast.parse((pt_hook.PKG / rel).read_text(encoding="utf-8")))
        assert set(quals) <= set(defs), rel


def test_the_hook_functions_are_derived_by_the_scan():
    """Item 10 of the review: the scan finds the plan's 123 hook-function candidates in 35 modules (73 producers), and
    every producer it finds has exactly one disposition: a new producer without one, or a stale one, fails closed."""
    cands = pt_scan.candidates()
    assert (len(cands), len({rel for rel, _ in cands})) == (123, 35)
    assert sum(kind == "producer" for kind in cands.values()) == len(pt_scan.PRODUCER_DISPOSITIONS) == 73
    assert set(pt_scan.PRODUCER_DISPOSITIONS.values()) == pt_scan.DISPOSITIONS


@pytest.mark.parametrize("change", ["missing", "stale", "unknown"])
def test_a_producer_the_dispositions_do_not_match_fails_the_scan(monkeypatch, change):
    table = dict(pt_scan.PRODUCER_DISPOSITIONS)
    if change == "missing":
        del table[("maps/slices.py", "body")]
    elif change == "stale":
        table[("engine/outbox.py", "no_such_function")] = "not worker text"
    else:
        table[("maps/slices.py", "body")] = "worker-ish text"
    monkeypatch.setattr(pt_scan, "PRODUCER_DISPOSITIONS", table)
    pt_scan.hook_functions.cache_clear()
    try:
        with pytest.raises(pt_scan.ScanError):
            pt_scan.hook_functions()
    finally:
        pt_scan.hook_functions.cache_clear()


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


def _plans() -> dict[str, pt_hook.Plan]:
    return {rel: pt_hook.plan_module(rel, (pt_hook.PKG / rel).read_text(encoding="utf-8"),
                                     registry=pt_hook.Registry())[1] for rel in pt_hook.hook_modules()}


# Names in an output position that the hook wraps as the constant they hold (items 1 and 2 of the review): a module
# constant resolved by import, or a local bound only to constants (the plan's "reviewed change" to the classification,
# v10 §2.2). Pinned, so a new member needs review: (module, function, expression, line) -> the constants' lines.
PINNED_REFS = {
    ("cli/fields.py", "register", "HELP", 51): {33},
    ("harness/opencode/projection.py", "system_text", "edit", 130): {120, 121},
    ("knowledge/context.py", "_launch_contract", "TOKEN_PLACEHOLDER", 217): {25},
    ("maps/slices.py", "_unavailable", "HEADING", 161): {39},
    ("maps/slices.py", "frame", "HEADING", 252): {39},
}
# The help sites the hook leaves unresolved: a `help=` that names a `for` target over a tuple of constants. None is in
# the five rendered help texts today; the full help trace must resolve them (under the same review) or render every
# parser's help. Pinned, so a new one needs review.
PINNED_FOR_TARGET_HELP = {("cli/commands.py", 226), ("cli/work_commands.py", 569), ("cli/work_commands.py", 606)}


def test_the_names_bound_to_constants_are_pinned():
    """Item 2: every name the hook resolves to the constants it holds is in the pinned list, each constant keyed at
    its own line (item 1: a real line, never 0, also for an imported constant)."""
    lines_by_ref: dict[tuple[str, str, str, int], set[int]] = {}
    for rel in pt_hook.hook_modules():
        reg = pt_hook.Registry()
        _, plan = pt_hook.plan_module(rel, (pt_hook.PKG / rel).read_text(encoding="utf-8"), registry=reg)
        for key, (fn, expr, line) in plan.ref_sites.items():
            lines_by_ref[(rel, fn, expr, line)] = {reg.units[u]["line"] for u in plan.refs[key].values()}
    assert lines_by_ref == PINNED_REFS


def test_the_unresolved_for_target_help_sites_are_pinned():
    """Item 2's latent gap: help keywords naming a `for` target over constants, which the hook leaves unmarked."""
    found = set()
    for rel, quals in pt_hook.hook_modules().items():
        tree = ast.parse((pt_hook.PKG / rel).read_text(encoding="utf-8"))
        defs = pt_hook.qualnames(tree)
        for q in quals:
            targets = {t.id for n in ast.walk(defs[q]) if isinstance(n, ast.For)
                       and isinstance(n.iter, (ast.Tuple, ast.List)) for t in ast.walk(n.target)
                       if isinstance(t, ast.Name)}
            for n in ast.walk(defs[q]):
                if isinstance(n, ast.Call) and (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) in \
                        pt_hook.PARSER_CALLS:
                    found |= {(rel, kw.value.lineno) for kw in n.keywords if kw.arg in pt_hook.HELP_KEYWORDS
                              and isinstance(kw.value, ast.Name) and kw.value.id in targets}
    assert found == PINNED_FOR_TARGET_HELP


def test_every_reader_of_wrapped_module_data_is_a_hook_function():
    """Item 1: the hook replaces a module-level display with its wrapped copy, so every reader sees markers. That is
    sound only while every reader in src/aew is a hook function: in its own module, by import, or as an attribute."""
    hook = pt_hook.hook_functions()
    for rel, plan in _plans().items():
        mod = "aew." + rel[:-3].replace("/", ".")
        for name in plan.data:
            readers = []
            for p in sorted(pt_hook.PKG.rglob("*.py")):
                other = p.relative_to(pt_hook.PKG).as_posix()
                tree = ast.parse(p.read_text(encoding="utf-8"))
                aliases = {a.asname or a.name for st in ast.walk(tree) if isinstance(st, ast.ImportFrom)
                           and st.module == mod.rsplit(".", 1)[0] for a in st.names if a.name == mod.rsplit(".", 1)[1]}
                assert not any(isinstance(st, ast.ImportFrom) and st.module == mod and
                               any(a.name == name for a in st.names) for st in ast.walk(tree)), (other, name)
                for q, fn in pt_hook.qualnames(tree, strict=False).items():
                    for n in ast.walk(fn):
                        local = other == rel and isinstance(n, ast.Name) and n.id == name
                        attr = isinstance(n, ast.Attribute) and n.attr == name and isinstance(n.value, ast.Name) \
                            and n.value.id in aliases
                        if local or attr:
                            readers.append((other, q))
                if other == rel:  # a module-level reader outside every function
                    body = [st for st in tree.body if not isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                                          ast.ClassDef))]
                    uses = [n for st in body for n in ast.walk(st) if isinstance(n, ast.Name) and n.id == name
                            and isinstance(n.ctx, ast.Load)]
                    assert uses == [], (rel, name)
            assert readers and all(r in hook for r in readers), (rel, name, readers)


def _card(name: str) -> dict:
    import hashlib

    import yaml

    raw = (pt_hook.PKG / "roles/cards" / name).read_bytes()
    return {"path": f"aew/roles/cards/{name}", "sha256": hashlib.sha256(raw).hexdigest(),
            "content": yaml.safe_load(raw.decode("utf-8"))}


def test_a_pinned_card_is_wrapped_only_when_it_is_provably_the_built_in_file():
    """Item 4 (B2): the card's prose is wrapped as its YAML file's units only when the pin's sha256 is the file's and
    the pinned content equals the file's; a wrong sha256, wrong content or another path is never wrapped."""
    card = _card("engineer.yaml")
    assert pt_hook.pinned_card(card) == ("src/aew/roles/cards/engineer.yaml", card["content"])
    assert pt_hook.pinned_card({**card, "sha256": "0" * 64}) is None
    tampered = {**card["content"], "purpose": card["content"]["purpose"] + " then run it"}
    assert pt_hook.pinned_card({**card, "content": tampered}) is None
    assert pt_hook.pinned_card({**card, "path": ".aew/roles/engineer.yaml"}) is None
    assert pt_hook.pinned_card(None) is None


def _facts(authored: dict[str, frozenset[str]]) -> pt_trace.Facts:
    return pt_trace.Facts("implementer", pt_hook.SRC, "", frozenset(), frozenset(), frozenset(), authored, {}, (),
                          frozenset())


def _fenced(text: str, fence: str = "checks.unit.description") -> tuple[dict, dict]:
    entry = {"code": 0, "stdout": "- " + pt_hook.wrap_value(text, "v0") + "\n", "stderr": ""}
    return entry, {"units": {}, "values": {"v0": {"fence": fence, "kind": "fence"}}}


def test_a_fence_traces_only_its_authored_source_and_product_prose_in_it_is_a_unit():
    """F1: a fenced value must equal its authored source (F1b), and a span inside a verbatim product string constant
    kept in an authored file is that constant's unit, never the fence (F1a: `aew init`'s checks description)."""
    from aew.knowledge.manifest import DEFAULT_CHECKS

    product = DEFAULT_CHECKS["checks"]["unit"]["description"]
    entry, registry = _fenced(product)
    judged = pt_trace.judge("context show", entry, registry, _facts({"checks": frozenset({product})}))
    assert judged and {j.source for j in judged} == {"unit"}
    assert {j.detail for j in judged} == {f"src/aew/knowledge/manifest.py|<module>|{pt_hook.key_hash(product)}"}
    authored = "run the focused tests, then submit"
    entry, registry = _fenced(authored)
    judged = pt_trace.judge("context show", entry, registry, _facts({"checks": frozenset({authored})}))
    assert judged and {j.source for j in judged} == {"fence"}
    judged = pt_trace.judge("context show", entry, registry, _facts({"checks": frozenset({"something else"})}))
    assert judged and {j.source for j in judged} == {"untraced"}
    entry, registry = _fenced(authored, fence="subject.content")  # a field with no authored source yet
    judged = pt_trace.judge("context show", entry, registry, _facts({"checks": frozenset({authored})}))
    assert {j.source for j in judged} == {"untraced"}


def test_each_json_delivery_point_has_a_closed_key_list():
    """F2: a JSON key traces only through its delivery point's key list: the keys of the dict its result method
    returns, and a nested record's schema properties; never a key with whitespace."""
    keys = pt_trace.json_keys()
    assert set(keys) == set(pt_trace.JSON_RESULTS)
    assert {"/workspace", "/operations", "/expected_kinds"} <= keys["whoami"]
    assert "/evaluated_snapshot/workspace_id" in keys["check run"] and "/log" in keys["check run"]
    assert "/workspace" not in keys["check run"] and "/path" in keys["context pack"]
    assert not any(any(c.isspace() for c in k) for ks in keys.values() for k in ks)
    entry = {"code": 0, "stdout": '{"workspace": "x", "then run it": 1, "scratch": 2}', "stderr": ""}
    facts = pt_trace.Facts("implementer", pt_hook.SRC, "x", frozenset(), frozenset(), frozenset(), {}, keys, (),
                           frozenset())
    judged = {(j.span, j.source) for j in pt_trace.judge("whoami", entry, {"units": {}, "values": {}}, facts)}
    assert ("workspace", "field-name") in judged
    assert ("run", "untraced") in judged and ("scratch", "untraced") in judged
