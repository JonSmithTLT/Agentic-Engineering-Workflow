"""The one path encoder and resolver of the configuration projection (register F46.1, proposal §3.1a; D3, N2, N3).

A field's identity is an RFC 6901 JSON Pointer over the policy document. A key that may not be shown, and every
non-string key, is the segment `@i` (its index in its mapping): a display-only, masked extension, valid only under the
digest it was rendered with, never an edit target.
"""

from __future__ import annotations

import random
from typing import Any

from aew.harness import contract as K
from aew.policy import config_paths as P


def test_pointer_escaping_raw_keys():
    """N3: the RFC 6901 escape branch on raw keys, which the projection never shows (they fail the shape rule)."""
    assert P.escape("a/b") == "a~1b" and P.escape("a~b") == "a~0b" and P.escape("~1") == "~01"
    for raw in ("a/b", "a~b", "~1", "~01", "/~/", "plain"):
        assert P.unescape(P.escape(raw)) == raw, raw
    document = {"a/b": {"a~b": 1}, "~1": 2}
    for location in (("a/b",), ("a/b", "a~b"), ("~1",)):
        path = P.pointer(P.escape(k) for k in location)
        assert P.resolve(document, path) == location, path
    assert P.tokens("/a~1b/a~0b") == ["a~1b", "a~0b"] and P.pointer([]) == "" and P.tokens("") == []


def test_an_unshown_key_is_its_index_and_a_shown_one_its_text():
    secret = "sk-" + "synthetic0123456789abcdef"  # synthetic only
    assert K.credential_shaped(secret)
    document = {"profiles": {"standard": {"model": "m"}, secret: {"model": "m"}, "a.b": {}, "has space": {}}}
    assert P.encode(("profiles", "standard", "model"), document) == "/profiles/standard/model"
    assert P.encode(("profiles", secret, "model"), document) == "/profiles/@1/model"
    assert P.encode(("profiles", "a.b"), document) == "/profiles/a.b"  # a dot is part of a key, never a separator
    assert P.encode(("profiles", "has space"), document) == "/profiles/@3"
    assert P.label(document["profiles"], secret) == "@1" and P.label(document["profiles"], "standard") == "standard"
    assert not P.is_identity("/profiles/@1/model") and P.is_identity("/profiles/standard/model")


def test_non_string_keys_are_always_indexed():
    """N2: YAML `1:`, `true:` and `null:` keys are `@i`, so one never shares a pointer with the string key `"1"`."""
    document = {1: "int", "1": "str", None: "null", "x": [10, 20]}
    assert P.encode((1,), document) == "/@0"
    assert P.encode(("1",), document) == "/1"
    assert P.encode((None,), document) == "/@2"
    assert P.encode(("x", 1), document) == "/x/1"  # a list element is its index
    assert P.resolve(document, "/@0") == (1,) and P.resolve(document, "/1") == ("1",)


def test_resolve_accepts_only_canonical_indices():
    """R6, §3.1a: one location has one accepted spelling. An index (and the digits after `@`) is RFC 6901's
    `0|[1-9][0-9]*` in ASCII; a leading zero, a non-ASCII digit or a superscript is not a path: `KeyError`, never an
    alias and never another exception."""
    document = {"provider_env": ["A", "B"], "profiles": {"a": 1, "b": 2}}
    assert P.resolve(document, "/provider_env/1") == ("provider_env", 1)
    assert P.resolve(document, "/profiles/@1") == ("profiles", "b")
    for path in ("/provider_env/01", "/provider_env/١", "/provider_env/²", "/provider_env/+1",
                 "/provider_env/ 1", "/provider_env/2", "/profiles/@01", "/profiles/@١", "/profiles/@¹",
                 "/profiles/@", "/profiles/@2", "no-leading-slash"):
        try:
            P.resolve(document, path)
        except KeyError:
            continue
        raise AssertionError(f"{path!r} resolved")
    for path in ("/provider_env/0", "/provider_env/1"):  # an accepted `@`-free path re-encodes to itself
        assert P.encode(P.resolve(document, path), document) == path


def test_an_absent_field_is_encoded_by_its_schema_name():
    assert P.encode(("steering", "envelope", "repetition_n"), {}) == "/steering/envelope/repetition_n"


KEY_ALPHABET = ["a", "b", "Z", "0", "9", ".", "/", "~", "-", "_", ":", " ", "é", "ß", "中", "@", "\n"]


def random_key(rng: random.Random) -> Any:
    roll = rng.random()
    if roll < 0.1:
        return rng.choice([0, 1, 7, True, None])
    return "".join(rng.choice(KEY_ALPHABET) for _ in range(rng.randint(1, 6)))


def random_document(rng: random.Random, depth: int = 0) -> Any:
    if depth > 3 or rng.random() < 0.25:
        return rng.choice([1, "v", None, True, 2.5])
    if rng.random() < 0.2:
        return [random_document(rng, depth + 1) for _ in range(rng.randint(0, 3))]
    return {random_key(rng): random_document(rng, depth + 1) for _ in range(rng.randint(0, 4))}


def locations(node: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    out = [prefix]
    if isinstance(node, dict):
        for k, v in node.items():
            out += locations(v, (*prefix, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += locations(v, (*prefix, i))
    return out


def mapping_keys(document: Any, location: tuple[Any, ...]) -> list[Any]:
    """The steps of ``location`` that are mapping keys (not list indices)."""
    out, node = [], document
    for step in location:
        if isinstance(node, dict):
            out.append(step)
        node = node[step]
    return out


def test_path_round_trip():
    """D3's proof, as a seeded property test over generated documents whose keys hold `.`, `/`, `~`, unicode, `@`,
    whitespace and non-string keys: every location encodes to a path that resolves back to it, an `@`-free path
    re-encodes to itself, and every unshown key is masked."""
    rng = random.Random(46_1)
    seen_identity = seen_masked = 0
    for _ in range(400):
        document = random_document(rng)
        for location in locations(document):
            path = P.encode(location, document)
            assert P.resolve(document, path) == location, (document, location, path)
            assert P.encode(P.resolve(document, path), document) == path
            keys = mapping_keys(document, location)
            if P.is_identity(path):
                seen_identity += 1
                assert all(P.shown_key(k) for k in keys), (location, path)
            else:
                seen_masked += 1
                assert not all(P.shown_key(k) for k in keys), (location, path)
    assert seen_identity > 100 and seen_masked > 100  # both branches were exercised
