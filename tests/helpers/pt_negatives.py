"""Negative controls for the pack-truth gate (F4 of the prototype's review): one planted string per judge branch that
must come out UNTRACED, so a branch that accepts too much fails the gate. Positive controls alone cannot show that a
branch is too wide.

Each plant is a product edit made at run time in the hooked process, where the product itself would make it (pt_hook's
INPUT_EDITS and MODULE_EDITS), never an edit of the tree. Each carries its own token (``AEW_PT_NEG_*``, a span of the
pattern) or, for the help plant, prose whose every span is also a CLI identifier, so it would pass a text match.

The whitespace plants (``yaml-ws``, ``plus-ws``) are different: they put whitespace around a data value and its
YAML leaf, and the cell invariant (``pt_trace.whitespace_inside``) must find none of it inside a data marker.

The branch each guards (the judge's ways of saying "traced"; pt_trace.judge):
| plant          | branch                                | it must come out             |
|----------------|---------------------------------------|------------------------------|
| fence-edit     | fence (the accessor)                  | untraced                     |
| value-unregistered | value (the closed site list)      | untraced                     |
| value-refused  | value (the class accessor)            | untraced                     |
| ref-rebound    | unit by name (the runtime equality)   | untraced                     |
| data-mutated   | unit by module data (leaf equality)   | untraced                     |
| json-key       | field name (the closed key list)      | untraced                     |
| json-value     | JSON field (the class accessor)       | untraced                     |
| help-prose     | CLI identifier (positional marks)     | untraced                     |
| cli-metavar    | CLI identifier (the live parser's)    | untraced                     |
| yaml-ws        | YAML unit (whitespace outside)        | no whitespace inside a marker|
| plus-ws        | ``+`` value (whitespace outside)      | no whitespace inside a marker|
The card plant (the pin's sha256 and content check) is made on the state copy itself: pt_harness.tamper_card.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pt_hook

FENCE_EDIT = " (AEW_PT_NEG_FENCE: then run it)"
UNREGISTERED = "AEW_PT_NEG_VALUE then run it"
REFUSED = "AEW_PT_NEG_ACCESSOR then run it"
REBOUND = "<AEW_PT_NEG_REF then run it>"
MUTATED = "AEW_PT_NEG_DATA then run it"
KEY_PROSE, KEY_NAME = "then run AEW_PT_NEG_KEY", "AEW_PT_NEG_KEYNAME"
JSON_VALUE = "AEW_PT_NEG_JSON then run it"
HELP = "submit the report, then run whoami"  # every span here is also a CLI identifier: a text match would pass it
METAVAR = "AEW_PT_NEG_META"
INSTALLED: set[str] = set()
YAML_WS_TOKEN = "AEW_PT_WS_YAML \n"  # the trailing whitespace is the plant
PLUS_WS = " padded "
YAML_WS_LEAF = ("src/aew/roles/archetypes/{role}.yaml", "responsibilities[1]")


def _computed(*parts: str) -> str:
    """Text a non-hook function computes: never a code constant."""
    return "".join(parts)


def _title(inputs: Any) -> None:
    inputs.title = inputs.title + _computed(FENCE_EDIT)


def _specialty(inputs: Any) -> None:
    inputs.specialty = _computed(UNREGISTERED)


def _workspace(inputs: Any) -> None:
    inputs.workspace = _computed(REFUSED)


def _outputs(inputs: Any) -> None:
    if inputs.card is not None:
        inputs.card = {**inputs.card, "outputs": [*(inputs.card.get("outputs") or []), PLUS_WS]}


def _token_placeholder(module: Any) -> None:
    module.TOKEN_PLACEHOLDER = _computed(REBOUND)


def _templates(module: Any) -> None:
    for _, template in module.OUTPUT_TEMPLATES.values():
        template["claim"] = _computed(MUTATED)


def _whoami(module: Any) -> None:
    original = module.Harness.invocation_whoami

    def invocation_whoami(self: Any, **kw: Any) -> dict[str, Any]:
        out = original(self, **kw)
        return {**out, "workspace": _computed(JSON_VALUE), KEY_PROSE: True, KEY_NAME: 1}

    module.Harness.invocation_whoami = invocation_whoami


def _help(module: Any) -> None:
    original = module.build_parser

    def build_parser(*a: Any, **kw: Any) -> Any:
        parser = original(*a, **kw)
        for action in parser._actions:
            if hasattr(action, "choices") and isinstance(action.choices, dict) and "whoami" in action.choices:
                whoami = action.choices["whoami"]
                if "help-prose" in INSTALLED:
                    whoami.add_argument("--pt-neg", help=_computed(HELP, " AEW_PT_NEG_HELP"))
                if "cli-metavar" in INSTALLED:  # argparse prints it, but the product's parser has no such identifier
                    whoami.add_argument("--pt-neg-meta", metavar=_computed(METAVAR))
        return parser

    module.build_parser = build_parser


PLANTS: dict[str, tuple[str, Callable[[Any], None]]] = {
    "fence-edit": ("inputs", _title),
    "value-unregistered": ("inputs", _specialty),
    "value-refused": ("inputs", _workspace),
    "plus-ws": ("inputs", _outputs),
    "ref-rebound": ("aew.knowledge.context", _token_placeholder),
    "data-mutated": ("aew.knowledge.context", _templates),
    "json-key": ("aew.engine.harness_ops", _whoami),
    "json-value": ("aew.engine.harness_ops", _whoami),
    "help-prose": ("aew.cli.main", _help),
    "cli-metavar": ("aew.cli.main", _help),
}


def install(names: list[str]) -> None:
    """Install the named plants in this process (after pt_hook.install, before anything imports aew)."""
    done: set[Callable[[Any], None]] = set()
    INSTALLED.update(names)
    for name in names:
        where, edit = PLANTS[name]
        if edit in done:
            continue
        done.add(edit)
        if where == "inputs":
            pt_hook.INPUT_EDITS.append(edit)
        else:
            pt_hook.MODULE_EDITS.setdefault(where, []).append(edit)
