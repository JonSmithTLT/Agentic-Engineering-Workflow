"""The one home of credential-shape literals (register F46.1, proposal §7 rule 8; p1, p3, q3, Q4).

`aew.harness.contract` holds every credential-shape pattern: the strict, case-sensitive `CREDENTIAL_PATTERNS` a
configuration projection withholds on, and the broader `REDACTION_FORMS` the OpenCode adapter redacts provider
messages with. The adapter's `KEY_SHAPED` and `LONG_TOKEN` are built from them. Every synthetic value here is built at
run time from obviously synthetic parts, and checked against the pattern it claims to match.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from credential_shapes import prefix, synthetic

from aew.harness import contract as K
from aew.harness.opencode import adapter

SRC = Path(K.__file__).resolve().parents[1]  # src/aew
HOME = Path(K.__file__).resolve()


SYNTHETIC = {p: synthetic(p) for p in K.CREDENTIAL_PATTERNS}


def test_each_synthetic_value_matches_its_pattern_and_is_credential_shaped():
    for pattern, value in SYNTHETIC.items():
        assert re.fullmatch(pattern, value), (pattern, value)
        assert K.credential_shaped(value) and K.credential_shaped(f"key: {value} (synthetic)"), value


def test_credential_patterns_no_false_positives():
    """p1, Q4: prose naming a prefix, names shaped like one, hyphenated names without a digit, dated model ids and a
    git sha stay shown."""
    for text in ("the `sk-` key", "AKIA prefixes", "sk-fast", "sk-implementer-review-fast", "vendor/model-2025-08-07",
                 "maker/model-2024-11-20-preview", "4f0a7101c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7", "risk-class",
                 "openai/gpt-5.1-codex-max-2025-11-20-preview-extended"):
        assert not K.credential_shaped(text), text


def test_the_token_boundary_is_rule_8s_not_a_word_boundary():
    """A match starts at the string's start or after a character outside [A-Za-z0-9_-]: `-` is not a boundary (a
    regex `\\b` would be), and a space or a slash is."""
    value = SYNTHETIC[K.CREDENTIAL_PATTERNS[0]]
    assert K.credential_shaped(value) and K.credential_shaped(f"x {value}") and K.credential_shaped(f"a/{value}")
    for glued in (f"fast-{value}", f"x{value}", f"_{value}", f"9{value}"):
        assert not K.credential_shaped(glued), glued


def string_constants(tree: ast.AST) -> list[str]:
    """Every string constant of a module except docstrings (comments are not in the syntax tree)."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


LITERAL = re.compile("|".join(K.at_token_boundary(prefix(p)) for p in K.CREDENTIAL_PATTERNS))


def literal_hits(text: str) -> list[str]:
    return [m.group(0) for m in LITERAL.finditer(text)]


def test_the_literal_check_matches_at_rule_8s_boundary():
    assert literal_hits("risk-class") == []  # engine/gates.py's "risk-class" is not an `sk-` literal
    assert literal_hits("x sk-abc") == ["sk-"]
    assert literal_hits("AKIA") == ["AKIA"] and literal_hits("pre_AKIA") == []


def test_single_credential_pattern_home():
    """p3: no credential-shape literal in any string constant in src/ outside `aew.harness.contract`."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        if path.resolve() == HOME:
            continue
        for text in string_constants(ast.parse(path.read_text(encoding="utf-8"))):
            found += [(path.relative_to(SRC).as_posix(), hit) for hit in literal_hits(text)]
    assert found == [], found
    assert any(literal_hits(t) for t in string_constants(ast.parse(HOME.read_text(encoding="utf-8"))))


def test_the_adapter_takes_its_forms_from_the_home():
    """`KEY_SHAPED` is the alternation of the home's scoped forms and its strict patterns; `LONG_TOKEN` and its
    predicate are the home's. The adapter's existing redaction test is the "no narrowing" check
    (tests/integration/test_opencode_adapter.py)."""
    assert adapter.LONG_TOKEN is K.LONG_TOKEN
    alternatives = [f.pattern for f in K.REDACTION_FORMS.values() if f.applies is None] + list(K.CREDENTIAL_PATTERNS)
    assert adapter.KEY_SHAPED.pattern == "|".join(alternatives)
    for value in SYNTHETIC.values():  # every strict shape is redacted from a kept message too
        assert value not in adapter.redact_key_shaped(f"upstream said {value} bad")


def test_redaction_forms_scoped_flags():
    """q3: the broader forms stay case-insensitive in the adapter; the strict patterns stay case-sensitive in F1; no
    pattern string in the home starts with a global inline flag."""
    assert adapter.redact_key_shaped("BEARER abc") == "<redacted>"
    assert adapter.redact_key_shaped("SK-abc") == "<redacted>"
    sk = next(p for p in K.CREDENTIAL_PATTERNS if p.startswith("sk-"))
    upper = SYNTHETIC[sk].replace("sk-", "SK-", 1)
    assert len(upper) == len(SYNTHETIC[sk]) and not K.credential_shaped(upper)
    for pattern in [*K.CREDENTIAL_PATTERNS, *(f.pattern for f in K.REDACTION_FORMS.values())]:
        assert not re.match(r"\(\?[aiLmsux]+\)", pattern), pattern


@pytest.mark.parametrize("token,redacted", [
    ("Zx9Qk2Lm7Np4Rs8Tv1Wy6Bc3Df5Gh0Jk2Mn4Pq6R", True),  # mixed case and digits
    ("4f0a7101c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7", False),  # a git sha: one case
    ("req_0123456789abcdef0123456789abcdef", False),
])
def test_the_long_token_form_keeps_its_predicate(token, redacted):
    assert K.REDACTION_FORMS["long_token"].applies is K.mixes_case_and_digits
    assert (token not in adapter.redact_key_shaped(f"failed on {token}")) is redacted
