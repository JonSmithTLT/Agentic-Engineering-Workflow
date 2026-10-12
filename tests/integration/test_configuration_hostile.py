"""The configuration projection over a hostile corpus: the class check that nothing withheld escapes, in any channel
(register F46.1, the proposal's §7; adopted from the F1a review's corpus as the class rule asks).

Each synthetic document is rendered through every channel F1a has: the engine's index and execution projection as
JSON, any exception's text, and the CLI's text and `--json` output on stdout and stderr. In every case:
- no planted marker appears: a credential-shaped value, an upper-cased variant, a credential-shaped variable name, or a
  key text that fails rule 5;
- the read raises nothing and the CLI exits 0;
- every FieldValue holds §3.1's four-case table;
- a document in force never carries violations;
- every emitted string fits Appendix A's bound (512 bytes, 256 for a path).
"""

from __future__ import annotations

import json
import traceback
from typing import Any

import pytest
from conftest import run_aew
from test_configuration_projection import (
    POLICY,
    SECRET,
    _with_manifest_policy,
    configured,
    field_values,
    fieldvalue_problems,
    long_strings,
    new_engine,
    pin_now,
)

from aew.engine import configuration as C
from aew.engine.api import Engine
from aew.harness import contract as K

UNSAFE = "unsafe key~/\u00fc"  # fails rule 5's shape: never shown
GH = "github_pat_" + "Synthetic0Test1Value2Only3"  # a valid variable name that is credential-shaped (synthetic)
assert K.credential_shaped(GH) and K.credential_shaped(SECRET)

P = POLICY | {"profiles": {"standard": {"model": "vendor/model-standard", "effort": "high"},
                           "review": {"provider": "other", "model": "model-review"}},
              "routing": {"default": "standard", "cards": {"researcher": "review"}}}
R = {"routing": {"default": "standard"}}
CASES: dict[str, Any] = {
    # keys
    "cred_profile_key_nested": P | {"profiles": {"standard": {"model": "v/m"},
                                                  SECRET: {"model": "v/m", "max_steps": "many", SECRET: 1}}},
    "cred_profile_key_valid": P | {"profiles": {"standard": {"model": "v/m"}, SECRET: {"model": "v/m"}},
                                   "routing": {"default": SECRET, "cards": {SECRET: SECRET}}},
    "unsafe_profile_key": P | {"profiles": {"standard": {"model": "v/m"}, UNSAFE: {"model": "v/m", "bad": 1}}},
    "at_key": P | {"profiles": {"standard": {"model": "v/m"}, "@0": {"model": "v/m"}}},
    "tilde_slash_card": P | {"routing": {"default": "standard", "cards": {"a/b": "standard", "a~b": "standard",
                                                                          UNSAFE: "standard"}}},
    "nonstring_keys": ("schema: aew/execution/v1\nconfigured: true\nprofiles:\n  1: {model: v/m}\n  '1': {model: v/m}\n"
                       "  true: {model: v/m}\n  null: {model: v/m}\nrouting: {default: '1'}\n"),
    "cred_top_extra_key": P | {SECRET: SECRET},
    "cred_nested_extra_keys": P | {"notify": {SECRET: 1, "command": [SECRET]},
                                   "containment": {"mode": "required", SECRET: [SECRET], "writable": [SECRET]}},
    "cred_classes_key": P | {"routing": {"default": "standard", "classes": {SECRET: "standard"}}},
    "cred_deep": P | {"profiles": {SECRET: {"model": {SECRET: [SECRET, {SECRET: SECRET}]}}}},
    # values
    "cred_values_valid": P | R | {"description": SECRET, "harness": SECRET,
                                  "profiles": {"standard": {"model": "v/" + SECRET, "provider": "v", "effort": SECRET,
                                                            "description": "x " + SECRET}},
                                  "provider_env": ["VENDOR_API_KEY", GH]},
    "cred_type_violation": P | {"configured": SECRET,
                                "profiles": {"standard": {"model": "v/m", "max_steps": SECRET}}},
    "cred_pattern_violation": P | {"profiles": {"standard": {"model": "v/m " + SECRET, "provider": "x/" + SECRET}}},
    "cred_enum_violation": P | {"steering": {"mode": SECRET}, "maps": {"pack_slices": SECRET}},
    "cred_const_violation": P | {"schema": SECRET},
    "cred_route_target_bad_name": P | {"routing": {"default": SECRET.upper(), "cards": {"c": "x " + SECRET}}},
    "cred_semantic_target": P | {"routing": {"default": "standard", "cards": {"c": SECRET}}},
    "cred_provider_env_invalid": P | {"provider_env": ["OK_NAME", "bad " + SECRET, 7]},
    "cred_conflict_suggestion": P | R | {"profiles": {"standard": {"provider": "other", "model": "vendor/" + SECRET}}},
    # over the bound
    "oversized_values": P | R | {"description": "d" * 5000,
                                 "profiles": {"standard": {"model": "v/m", "effort": "e" * 3000,
                                                           "description": "p" * 5000}},
                                 "provider_env": ["V" * 3000]},
    # YAML
    "yaml_mark": f"profiles: [\n  {SECRET}: x\n  - b\n",
    "yaml_tab_mark": f"a:\n\t{SECRET}\n",
    "yaml_unhashable": f"? [{SECRET}]\n: 1\n",
    "yaml_alias_bomb": ("a: &a [x,x,x,x,x,x,x,x,x]\nb: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
                        "c: [*b,*b,*b,*b,*b,*b,*b,*b,*b]\n"),
    "yaml_python_tag": f"a: !!python/object/apply:os.system ['{SECRET}']\n",
    "yaml_dup_key": f"configured: true\nconfigured: {SECRET}\n",
    "non_utf8": b"description: \xff\xfe " + SECRET.encode() + b"\n",
    "not_a_mapping": f"- {SECRET}\n",
    "empty": "",
    "deep_nesting_3000": "description: " + "[" * 3000 + SECRET + "]" * 3000 + "\n",
    # the execution policy's file, also named by a later manifest key
    "shared_schema_invalid": P | R | {"profiles": {"standard": {"model": "v/m", "max_steps": SECRET}}},
    "shared_profile_without_model": P | R | {"profiles": {"standard": {"effort": "high"}}},
    "shared_profiles_as_list": P | R | {"profiles": [SECRET]},
}
SHARED = {"shared_schema_invalid", "shared_profile_without_model", "shared_profiles_as_list"}
MARKERS = (SECRET, SECRET.upper(), GH, UNSAFE, "unsafe key")


def render(e: Engine) -> tuple[str, dict[str, Any], list[str]]:
    """Every channel's text, the execution projection, and what went wrong (an exception, a non-zero exit)."""
    texts, problems, execution = [], [], {}
    for document in (None, "execution"):
        try:
            out = Engine.discover(e.repo_root).configuration(document)
            texts.append(json.dumps(out, ensure_ascii=False, default=str))
            execution = out if document else execution
        except Exception as exc:  # an exception is a channel too
            texts.append("".join(traceback.format_exception(exc)))
            problems.append(f"the engine raised {type(exc).__name__}")
    for args in (["settings", "show", "execution"], ["settings", "show", "--json"]):
        res = run_aew("-C", str(e.repo_root), *args)
        texts.append(res.stdout + res.stderr)
        if res.returncode != 0:
            problems.append(f"`aew {' '.join(args)}` exited {res.returncode}")
    return "\n".join(texts), execution, problems


@pytest.mark.parametrize("case", sorted(CASES))
def test_nothing_withheld_escapes_a_hostile_document(tmp_path, case):
    e = new_engine(tmp_path)
    if case in SHARED:
        _with_manifest_policy(e, zz_alias="policy/execution.yaml")
    policy = CASES[case]
    if isinstance(policy, bytes):  # not text: written as is, then pinned
        (e.aew_root / "policy/execution.yaml").write_bytes(policy)
        pin_now(e)
    else:
        configured(e, policy)
    text, execution, problems = render(e)
    assert problems == []
    assert [m for m in MARKERS if m in text] == []
    assert [p for fv in field_values(execution) for p in fieldvalue_problems(fv)] == []
    document = execution["document"]
    assert not (document["in_force"] and document["state"] != C.ABSENT and document["violations"]), document
    assert long_strings(execution) == []


def test_the_deep_document_is_one_structured_violation(tmp_path):
    """R3: a nesting deep enough to exhaust the recursion limit is one violation at the root, not an exception."""
    e = configured(new_engine(tmp_path), CASES["deep_nesting_3000"])
    out = Engine.discover(e.repo_root).configuration("execution")
    assert out["document"]["state"] == C.INVALID
    assert out["document"]["violations"] == [C.UNPROCESSABLE_VIOLATION] and out["profiles"] == []
