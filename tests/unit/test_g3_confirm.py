"""The G3 confirmer's core, on every platform (A-37 G3-03, G3-05; STG-03, G3-B): the facts it restates, held to their
owners; what it shows of a pending approval; the decisions it sends; and the Python it must run on.

The confirmer runs under the host's own Python 3 (Rocky 8's platform-python, 3.6), which CI does not have. These tests
run its code under CI's Python, and two static detectors below keep it within 3.6's language and standard library:
the parser at its lowest version, and a list of the 3.7-and-later names the parser cannot see. The live proof is the
run under platform-python on the Rocky 8 VM, recorded in the pull request (tests/helpers/g3_confirm_py36.py).
"""

from __future__ import annotations

import ast
import copy
import json
import re
from typing import Any

import pytest

from aew_g3 import COMMAND, CONFIRM_SOCK, ROOT, cli, wire
from aew_g3_confirm import core
from tests.helpers import g3 as G

PACKAGE = ROOT / "aew_g3_confirm"
SOURCES = [*sorted(PACKAGE.glob("*.py")), G.REPO / "tests" / "helpers" / "g3_confirm_py36.py"]  # all run on 3.6


# ------------------------------------------------------------------------------------------------ restated facts
def test_the_confirmers_restated_facts_are_their_owners() -> None:
    """Derive, don't restate: aew_g3 needs Python 3.11, so the confirmer restates these, and this test holds them."""
    assert core.CONFIRM_SOCK == (cli.RUNTIME_DIR / CONFIRM_SOCK).as_posix()
    assert (core.WIRE_HEADER, core.WIRE) == (wire.HEADER, wire.WIRE)
    assert core.MAX_LINES == wire.schema()["$defs"]["PendingApproval"]["properties"]["rendering"]["maxItems"]
    assert core.COMMAND == COMMAND and COMMAND in core.MESSAGES["PIN_LOCKED"]
    codes = set(core.MESSAGES) - {core.APPROVED, core.DECLINED}
    assert codes <= set(wire.STATUS), codes - set(wire.STATUS)
    decision = wire.schema()["$defs"]["ApprovalDecision"]
    assert set(decision["properties"]["decision"]["enum"]) == {"APPROVE", "DECLINE"}


def _install_value(install: str, name: str) -> str:
    found = re.findall(rf"^{name}=(\S+)", install, re.M)
    assert len(found) == 1, (name, found)
    return found[0]


def test_install_sh_and_both_desktop_entries_launch_the_same_confirmer_from_the_pinned_path() -> None:
    """Addendum 4: the menu entry and the autostart entry are root's, hold no code and no values, and name only the
    executable under the install root; each is named for the application id, as the desktop's notifications need."""
    install = (ROOT / "install.sh").read_bytes().decode()
    confirm, install_root = _install_value(install, "CONFIRM"), _install_value(install, "ROOT")
    assert confirm.startswith(install_root + "/")  # G3-14: under the one root-owned path
    menu = ROOT / "desktop" / (core.APP_ID + ".desktop")
    login = ROOT / "desktop" / "autostart" / (core.APP_ID + ".desktop")
    assert sorted(p.relative_to(ROOT / "desktop").as_posix() for p in (ROOT / "desktop").rglob("*") if p.is_file()) \
        == sorted([menu.name, "autostart/" + login.name])
    for entry, exec_line in ((menu, confirm), (login, confirm + " " + core.AT_LOGIN)):  # no other argument (G3-05)
        text = entry.read_bytes().decode()
        assert re.findall(r"^Exec=(.*)$", text, re.M) == [exec_line], entry.name
        assert set(re.findall(r"^(\w[\w-]*)=", text, re.M)) <= {
            "Type", "Name", "Comment", "Exec", "Terminal", "Categories", "NoDisplay", "X-GNOME-Autostart-enabled"}
    assert _install_value(install, "DESKTOP") == "/usr/share/applications/" + menu.name
    assert _install_value(install, "AUTOSTART") == "/etc/xdg/autostart/" + login.name
    assert 'cp "$HERE/desktop/autostart/' + login.name + '" "$AUTOSTART"' in install
    assert 'chmod 0644 "$DESKTOP" "$AUTOSTART"' in install
    assert re.search(r"^exec \$CONFIRM_PY -I -B -c '.*from aew_g3_confirm\.window import main.*' \"\\\$@\"$",
                     install, re.M)
    assert 'cp "$HERE"/aew_g3_confirm/*.py "$ROOT/aew_g3_confirm/"' in install


# ------------------------------------------------------------------------------------------------ G3-03 what is shown
def _p1() -> dict[str, Any]:
    return copy.deepcopy(G.P1["pending"])


def test_each_served_line_is_one_row_made_only_of_its_own_fields_and_a_fixed_label() -> None:
    """Hand-off G3-B item 2: every line, and no other text. A template line shows its template_id; a typed field shows
    its field_path and its value as JSON; an owner fact shows its owner, fact, observation and values."""
    pending = _p1()
    rendering = pending["rendering"]
    got = core.rows(pending)
    assert len(got) == len(rendering)
    assert {ln["source"]["kind"] for ln in rendering} == {"TEMPLATE", "TYPED_FIELD", "OWNER_FACT"}  # control
    for (label, value), line in zip(got, rendering, strict=True):
        source = line["source"]
        if source["kind"] == "TEMPLATE":
            assert (label, value) == (core.LABEL_ACTION, line["template_id"])
        elif source["kind"] == "TYPED_FIELD":
            assert (label, value) == (source["field_path"], json.dumps(line["values"]["value"]))
        else:
            parts = [json.dumps(source[k]) for k in ("owner", "fact_ref", "observation_state", "observed_at")]
            assert (label, value) == (core.LABEL_FACT, " ".join(parts) + " " + json.dumps(line["values"],
                                                                                       sort_keys=True))
        assert label in core.LABELS or label == source.get("field_path")


def test_a_value_shows_its_type_and_every_character_that_could_disguise_it_escaped() -> None:
    assert [core.shown(v) for v in (None, "null", True, "true", 7, "7")] == \
        ["null", '"null"', "true", '"true"', "7", '"7"']
    for disguise in ("‮", "​", "а", "\n", "\x1b"):  # RTL override, zero width, Cyrillic a, controls
        assert disguise not in core.shown("lead" + disguise + "x") and core.shown("lead" + disguise + "x").isascii()


def test_a_rendering_of_243_lines_shows_243_rows_and_one_more_or_none_is_refused() -> None:
    pending = _p1()
    field = next(ln for ln in pending["rendering"] if ln["source"]["kind"] == "TYPED_FIELD")
    pending["rendering"] = [field] * core.MAX_LINES
    assert len(core.rows(pending)) == core.MAX_LINES
    for n in (core.MAX_LINES + 1, 0):
        pending["rendering"] = [field] * n
        with pytest.raises(core.Malformed):
            core.rows(pending)


@pytest.mark.parametrize("edit", [
    "template_with_values", "typed_name_not_path", "typed_extra_value", "unknown_kind", "extra_line_key",
    "fact_without_observation", "line_not_object", "source_extra_key",
])
def test_a_line_the_confirmer_cannot_show_exactly_is_refused_whole_never_shown_in_part(edit: str) -> None:
    pending = _p1()
    lines = pending["rendering"]
    template = next(i for i, ln in enumerate(lines) if ln["source"]["kind"] == "TEMPLATE")
    typed = next(i for i, ln in enumerate(lines) if ln["source"]["kind"] == "TYPED_FIELD")
    fact = next(i for i, ln in enumerate(lines) if ln["source"]["kind"] == "OWNER_FACT")
    if edit == "template_with_values":
        lines[template]["values"] = {"note": "Routine maintenance, safe to approve"}
    elif edit == "typed_name_not_path":
        lines[typed]["values"]["name"] = "recipient_ref"
    elif edit == "typed_extra_value":
        lines[typed]["values"]["note"] = "safe"
    elif edit == "unknown_kind":
        lines[typed]["source"]["kind"] = "CLIENT_TEXT"
    elif edit == "extra_line_key":
        lines[typed]["prose"] = "safe"
    elif edit == "fact_without_observation":
        del lines[fact]["source"]["observation_state"]
    elif edit == "line_not_object":
        lines[typed] = "safe to approve"
    else:
        lines[template]["source"]["field_path"] = "recipient_ref"
    with pytest.raises(core.Malformed):
        core.rows(pending)


# ------------------------------------------------------------------------------------------------ G3-05 deciding
def test_approve_carries_the_pin_and_decline_carries_none_each_a_valid_decision_on_the_wire() -> None:
    approve, decline = (json.loads(core.decision_body(p)) for p in (G.PIN, None))
    assert approve == {"decision": "APPROVE", "pin": G.PIN} and decline == {"decision": "DECLINE"}
    assert not wire.wire_errors("ApprovalDecision", approve) and not wire.wire_errors("ApprovalDecision", decline)


def test_an_outcome_the_table_lacks_is_named_as_sent_and_never_reads_as_approved() -> None:
    assert core.message("SOMETHING_NEW") == "The service refused the decision: SOMETHING_NEW. Nothing was approved."
    # NOT_FOUND may follow an approval whose reply was lost (addendum 2 §1), so it alone claims nothing either way.
    said = {c: core.message(c).lower() for c in core.MESSAGES if c not in (core.APPROVED, "NOT_FOUND")}
    assert all("nothing was approved" in m for m in said.values()), said
    assert "approved" not in core.message("NOT_FOUND").lower()


# ------------------------------------------------------------------------------------------------ addendum 4
def _pending(*refs: str) -> list[dict[str, Any]]:
    return [{**_p1(), "approval_ref": r} for r in refs]


def test_each_pending_approval_is_notified_once_and_withdrawn_when_it_leaves_the_list() -> None:
    watch = core.Watch()
    assert watch.update(_pending("approval:a", "approval:b")) == (["approval:a", "approval:b"], [])
    assert watch.update(_pending("approval:a", "approval:b")) == ([], [])  # later polls do not repeat it
    assert watch.update(_pending("approval:b", "approval:c")) == (["approval:c"], ["approval:a"])
    assert watch.update([]) == ([], ["approval:b", "approval:c"])  # decided, expired, or lost to a restart
    assert watch.update(_pending("approval:b")) == (["approval:b"], [])  # back on the list: a new notification
    assert core.notification_id("approval:b") != core.notification_id("approval:c")


def test_the_notification_is_fixed_text_that_carries_nothing_from_the_request() -> None:
    p1 = _p1()
    served = {json.dumps(v) for ln in p1["rendering"] for v in ln["values"].values()}
    served |= {ln["template_id"] for ln in p1["rendering"]} | {p1["approval_ref"]}
    for text in (core.NOTIFY_TITLE, core.NOTIFY_BODY):
        assert not [s for s in served if s.strip('"') and s.strip('"') in text], text
    window = (PACKAGE / "window.py").read_bytes().decode()
    assert "add_button" not in window and "set_button" not in window  # no approve or decline button on it
    assert re.findall(r"Gio\.Notification\.new\(([^)]*)\)", window) == ["core.NOTIFY_TITLE"]
    assert re.findall(r"\.set_body\(([^)]*)\)", window) == ["core.NOTIFY_BODY"]


# Every call that opens, raises or focuses a window, and the one method allowed to make them: the operator's own act
# (a launch from the menu, or a notification's click). The poll never reaches it (addendum 4).
SHOWS = {"present", "present_with_time", "show", "show_all", "show_now", "grab_focus", "deiconify", "set_keep_above",
         "set_urgency_hint", "set_focus", "activate_focus", "maximize", "fullscreen", "stick"}


def _calls(node: ast.AST) -> list[ast.Attribute]:
    return [n.func for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]


def test_only_app_present_opens_raises_or_focuses_the_window_and_only_the_operators_acts_reach_it() -> None:
    tree = ast.parse((PACKAGE / "window.py").read_bytes().decode())
    shows: dict[str, set[str]] = {}
    callers = set()
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
            for f in _calls(fn):
                if isinstance(f.value, ast.Name) and f.value.id == "self" and f.attr == "present":
                    callers.add(cls.name + "." + fn.name)  # App's own present()
                elif f.attr in SHOWS:
                    shows.setdefault(cls.name + "." + fn.name, set()).add(f.attr)
    assert shows == {"App.present": {"show_all", "present"}}, shows  # control: it is found where it is
    # Its callers: the "show" action (a notification's click) and activate (a launch), never a poll.
    assert callers == {"App.__init__", "App._on_activate"}, callers
    poll = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in ("_poll", "_polled")]
    assert len(poll) == 2 and not {f.attr for fn in poll for f in _calls(fn)} & (SHOWS | {"_refresh"})


# ------------------------------------------------------------------------------------------------ Python 3.6
# The 3.7-and-later language and library the parser at feature_version (3, 7) cannot see, each named: the confirmer
# runs under Rocky 8's platform-python, 3.6.
AFTER_3_6 = {
    r"from __future__ import annotations": "postponed annotations (3.7)",
    r"\bdataclasses\b": "dataclasses (3.7)",
    r"\bcapture_output\b": "subprocess.run(capture_output=) (3.7)",
    r"\btext=True\b": "subprocess.run(text=) (3.7)",
    r"\bnullcontext\b": "contextlib.nullcontext (3.7)",
    r"\btime_ns\b": "time.time_ns (3.7)",
    r"\bbreakpoint\(": "breakpoint() (3.7)",
    r"\bimportlib\.resources\b": "importlib.resources (3.7)",
    r"\bcontextvars\b": "contextvars (3.7)",
    r"\basyncio\.run\b": "asyncio.run (3.7)",
    r"\bfromisoformat\b": "datetime.fromisoformat (3.7)",
    r"\bisascii\b": "str.isascii (3.7)",
    r"\bremoveprefix\b|\bremovesuffix\b": "str.removeprefix (3.9)",
    r"(?<![\w.])(list|dict|tuple|set|frozenset|type)\[": "builtin generics, list[int] (3.9)",
    r"\|\s*None\b": "X | None (3.10)",
}


def test_the_confirmer_parses_at_the_lowest_python_the_parser_knows() -> None:
    for f in SOURCES:
        ast.parse(f.read_bytes().decode(), filename=str(f), feature_version=(3, 7))
    assert {f.name for f in SOURCES} >= {"__init__.py", "core.py", "window.py"}


def test_the_confirmer_uses_nothing_python_3_6_lacks() -> None:
    found = [(f.name, why) for f in SOURCES for pattern, why in AFTER_3_6.items()
             if re.search(pattern, f.read_bytes().decode())]
    assert not found, found
    planted = "from __future__ import annotations\nimport dataclasses\n"  # control: the detector sees them
    assert sum(bool(re.search(p, planted)) for p in AFTER_3_6) == 2


def test_only_the_window_imports_gtk_and_nothing_imports_aew() -> None:
    for f in SOURCES:
        tree = ast.parse(f.read_bytes().decode())
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                  and not n.level}
        assert not names & {"aew", "aew_g3"}, (f.name, names)
        assert ("gi" in names) == (f.name == "window.py"), (f.name, names)
