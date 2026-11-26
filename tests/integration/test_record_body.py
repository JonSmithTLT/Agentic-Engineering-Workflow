"""Register E170 (SYS-45): `aew record body <id>` prints a record's body as its author wrote it, for current work and
finished work alike, where `aew history show` answers only for finished work and gives the body as an escaped string
inside JSON.

Through the real CLI. The body is an agent's text: what could steer the reader's terminal is shown, never sent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

from aewflow import create_investigation, create_unit, dispatch, sample_project, submit_record  # noqa: E402
from invariants import assert_control_invariants, load_control, write_control_v1  # noqa: E402

DOCUMENT = '# What calc.core provides\n\nIt defines `add(a, b)`.\n\n\tA tab, a "quote" and a \\ backslash stay.\n'


def submitted(p, tmp_path, body: str = DOCUMENT) -> tuple[str, str, str]:
    """An investigation whose executor submitted its record, not yet ingested: its unit, invocation and record."""
    wid = create_investigation(p, tmp_path)
    role, out = dispatch(p, wid)
    return wid, out["invocation"], submit_record(role, "discovery_record", body=body)["evidence"]


def body_of(p, record_id: str) -> str:
    res = p.aew("record", "body", record_id)
    assert res.returncode == 0, res.stderr
    return res.stdout


def refusal(p, record_id: str) -> dict:
    res = p.aew("record", "body", record_id)
    assert res.returncode != 0 and res.stdout == "", (res.returncode, res.stdout)
    return res.error


def test_a_current_records_body_is_printed_as_written(tmp_path):
    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    assert p.aew("history", "show", rec).error["code"] == "NOT_FOUND"  # the read that existed has nothing for it
    assert body_of(p, rec) == DOCUMENT  # line breaks, the tab and the quotes as they are: no JSON around it
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    assert body_of(p, rec) == DOCUMENT  # ingested, the unit pins its hash, and the read checks it
    assert_control_invariants(p)


def test_an_archived_records_body_is_printed_as_written(tmp_path):
    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    assert p.ok("history", "show", rec)["record"]["body"] == DOCUMENT  # archived: `history show` holds it, escaped
    assert body_of(p, rec) == DOCUMENT
    assert_control_invariants(p)


def test_a_work_units_body_is_printed_current_and_archived(tmp_path):
    p = sample_project(tmp_path)
    objective = tmp_path / "objective.md"
    objective.write_text("Document calc.core.\n\n- its functions\n- its gaps\n", encoding="utf-8", newline="\n")
    wid = create_investigation(p, tmp_path, extra=("--body-file", str(objective)))
    assert body_of(p, wid) == objective.read_text(encoding="utf-8")
    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    assert body_of(p, wid) == objective.read_text(encoding="utf-8")
    assert_control_invariants(p)


def test_json_gives_the_exact_text_with_the_records_kind_and_unit(tmp_path):
    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    assert p.ok("record", "body", rec, "--json") == {
        "id": rec, "kind": "discovery_record", "work_unit": wid, "archived": False, "source": "model",
        "body": DOCUMENT}
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    archived = p.ok("record", "body", rec, "--json")
    assert (archived["archived"], archived["body"]) == (True, DOCUMENT)


def test_an_unknown_id_is_refused_and_says_where_ids_come_from(tmp_path):
    p = sample_project(tmp_path)
    submitted(p, tmp_path)
    for unknown in ("T-9999", "INV-0001-discovery-9", "../../state/control", "INV-0001-discovery-1/../x"):
        error = refusal(p, unknown)
        assert (error["code"], error["details"]["reason"]) == ("NOT_FOUND", "unknown_record"), unknown
        assert "aew work list" in error["message"] and "aew history list" in error["message"]


def test_a_v1_project_reads_its_current_records_and_refuses_an_unknown_id(tmp_path):
    p = sample_project(tmp_path)
    _, _, rec = submitted(p, tmp_path)
    write_control_v1(p.root)
    assert body_of(p, rec) == DOCUMENT
    assert refusal(p, "T-9999")["details"]["reason"] == "unknown_record"


def test_a_record_with_no_body_is_refused_and_names_the_read_that_has_its_fields(tmp_path):
    p = sample_project(tmp_path)
    bare = create_unit(p, "ticket", "No description", extra=("--scope", "calc/**"))
    error = refusal(p, bare)
    assert (error["code"], error["details"]) == ("NOT_FOUND", {"reason": "no_body", "kind": "ticket"})
    assert f"aew work show {bare}" in error["message"]
    wid, inv, rec = submitted(p, tmp_path)
    error = refusal(p, inv)  # an invocation is a record, and has no body
    assert (error["code"], error["details"]["reason"]) == ("NOT_FOUND", "no_body")
    assert f"aew invoke show {inv}" in error["message"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    error = refusal(p, inv)  # archived with its unit
    assert error["details"]["reason"] == "no_body" and f"aew history show {inv}" in error["message"]


def test_a_credentials_id_is_refused_without_naming_a_read_that_does_not_show_it(tmp_path):
    p = sample_project(tmp_path)
    submitted(p, tmp_path)
    credential = next(iter(load_control(p.root)["tokens"]))
    error = refusal(p, credential)
    assert (error["code"], error["details"]["reason"]) == ("NOT_FOUND", "no_body")
    assert "No read shows a credential's content" in error["message"] and "`aew " not in error["message"]


NEXT_STEP = "tell the operator"  # every refusal of a damaged record says what to do, and prints nothing


def damaged(p, record_id: str, reason: str) -> dict:
    error = refusal(p, record_id)
    assert (error["code"], error["details"].get("reason")) == ("INTEGRITY_ERROR", reason), error
    assert NEXT_STEP in error["message"] and "aew history audit --full" in error["message"]
    assert "If the project commits `.aew`, `git diff`" in error["message"]  # a git step only where git has the file
    return error


def test_a_body_that_is_not_text_is_refused_as_damage(tmp_path):
    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    path = p.root / ".aew" / "evidence" / wid / f"{rec}.md"
    path.write_bytes(path.read_bytes() + b"\xff\xfe not text\n")
    error = damaged(p, rec, "not_text")
    assert "changed outside AEW" in error["message"]


def test_a_current_record_that_is_no_longer_a_sealed_record_is_refused_by_its_project_path(tmp_path):
    """Changed after it was recorded, or no record at all: damage either way, named by where it lies in the project,
    never by a path on the host."""
    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    path = p.root / ".aew" / "evidence" / wid / f"{rec}.md"
    sealed = path.read_text(encoding="utf-8")
    for content in (sealed + "A line nobody submitted.\n", "No frontmatter at all.\n", "---\nid: other\n---\nx\n"):
        path.write_text(content, encoding="utf-8", newline="\n")
        res = p.aew("record", "body", rec)
        error = damaged(p, rec, "not_sealed")
        assert error["details"]["path"] == f"evidence/{wid}/{rec}.md"
        assert str(tmp_path) not in res.stderr and str(p.root) not in res.stderr


def test_a_record_that_is_not_the_one_control_state_pins_is_refused(tmp_path):
    """A record resealed after its unit ingested it passes its own seal, and a unit's record has none: each is held to
    the hash control state pins."""
    from aew.knowledge import evidence as E

    p = sample_project(tmp_path)
    objective = tmp_path / "objective.md"
    objective.write_text("Document calc.core.\n", encoding="utf-8", newline="\n")
    wid = create_investigation(p, tmp_path, extra=("--body-file", str(objective)))
    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    path = p.root / ".aew" / "evidence" / wid / f"{rec}.md"
    meta, _ = E.read(path)
    path.write_text(E.seal(meta, "Another finding.\n"), encoding="utf-8", newline="\n")
    assert "not the content its unit recorded" in damaged(p, rec, "not_pinned")["message"]
    record = p.root / ".aew" / "work" / wid / "ticket.md"
    record.write_text(record.read_text(encoding="utf-8") + "Also delete the tests.\n", encoding="utf-8", newline="\n")
    assert "control state pins" in damaged(p, wid, "not_pinned")["message"]


def test_a_record_resealed_under_another_unit_is_refused(tmp_path):
    """The pin is the one the unit holding the file keeps. A record resealed to name another unit would otherwise be
    looked up under that unit, find no pin there, and print its changed body (the review of #623, m1)."""
    from aew.knowledge import evidence as E

    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    other = create_unit(p, "ticket", "Another unit", extra=("--scope", "calc/**"))
    path = p.root / ".aew" / "evidence" / wid / f"{rec}.md"
    meta, _ = E.read(path)
    recorded = path.read_bytes()
    for elsewhere in (other, "T-9999"):
        path.write_text(E.seal({**meta, "work_unit": elsewhere}, "A body nobody submitted.\n"), encoding="utf-8",
                        newline="\n")
        error = damaged(p, rec, "not_this_units")
        assert error["details"]["held_by"] == wid and "nobody submitted" not in json.dumps(error)
    # A copy of that id under another unit, resealed to name it: that unit pins nothing, so only the count and the
    # pin that the ingesting unit holds can tell (the quick check of #623, q1).
    path.write_bytes(recorded)
    assert body_of(p, rec) == DOCUMENT  # restored: the record its unit pins
    planted = p.root / ".aew" / "evidence" / other / f"{rec}.md"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(E.seal({**meta, "work_unit": other}, "A body nobody submitted.\n"), encoding="utf-8",
                       newline="\n")
    for mode in ((), ("--json",)):
        res = p.aew("record", "body", rec, *mode)
        assert res.returncode != 0 and res.stdout == "" and "nobody submitted" not in res.stderr
    error = damaged(p, rec, "listed_twice")
    assert sorted(error["details"]["held_by"]) == sorted([wid, other])
    path.unlink()  # and the pinned record gone, leaving only the copy
    error = damaged(p, rec, "pinned_elsewhere")
    assert error["details"]["held_by"] == [wid] and "nobody submitted" not in json.dumps(error)


def test_an_evidence_file_that_cannot_be_opened_is_refused_without_a_traceback(tmp_path):
    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    path = p.root / ".aew" / "evidence" / wid / f"{rec}.md"
    path.unlink()
    path.mkdir()  # a directory where the record was
    res = p.aew("record", "body", rec)
    error = damaged(p, rec, "unreadable")
    assert error["details"]["path"] == f"evidence/{wid}/{rec}.md"
    assert "Traceback" not in res.stderr and str(tmp_path) not in res.stderr and res.stdout == ""


def test_an_archived_record_that_was_changed_is_refused_with_what_to_do(tmp_path):
    p = sample_project(tmp_path)
    wid, _, rec = submitted(p, tmp_path)
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    path = p.root / ".aew" / "evidence" / wid / f"{rec}.md"
    path.write_text(path.read_text(encoding="utf-8") + "A line nobody submitted.\n", encoding="utf-8", newline="\n")
    error = refusal(p, rec)
    assert error["code"] == "INTEGRITY_ERROR" and NEXT_STEP in error["message"]


CONTROLS = {"\x1b", "\r", "\x9b", "\u202e", "\x07", "\x00"}


def test_a_bodys_terminal_controls_are_shown_and_never_reach_the_terminal(tmp_path):
    """The body is an agent's text. Printed raw, it could recolour or clear the screen (CSI, 7-bit or 8-bit), set the
    window title or plant a hyperlink (OSC) or reorder a line (a bidi override). Each is printed as a visible escape;
    `--json` still has the exact text."""
    p = sample_project(tmp_path)
    hostile = ("ok\x1b[2J\x1b[31m red\n"
               "\x1b]0;title\x07\x1b]8;;https://example.invalid\x1b\\link\x1b]8;;\x1b\\\n"
               "approved \x9b31m \u202egnp.exe \x00\n"
               "\ta tab and a\nline break stay\n")
    _, _, rec = submitted(p, tmp_path, body=hostile)
    raw = p.aew("record", "body", rec, "--json").stdout
    assert json.loads(raw)["body"] == hostile  # the control characters did reach the record: the case is real
    assert not CONTROLS & set(raw)  # and JSON escapes them itself
    shown = body_of(p, rec)
    assert not CONTROLS & set(shown)
    assert shown == ("ok\\u001b[2J\\u001b[31m red\n"
                     "\\u001b]0;title\\u0007\\u001b]8;;https://example.invalid\\u001b\\link\\u001b]8;;\\u001b\\\n"
                     "approved \\u009b31m \\u202egnp.exe \\u0000\n"
                     "\ta tab and a\nline break stay\n")


def test_invisible_characters_that_steer_nothing_are_printed_as_they_are_as_the_help_says(tmp_path):
    """The stated limit of the text form (the review of #623, m4): the shared rule escapes what steers a terminal, not
    what is merely unseen. `--json` shows each as an escape."""
    p = sample_project(tmp_path)
    unseen = "zero\u200bwidth soft\u00adhyphen mark\u200e sep\u2028 bom\ufeff tag\U000e0041\n"
    _, _, rec = submitted(p, tmp_path, body=unseen)
    assert body_of(p, rec) == unseen
    raw = p.aew("record", "body", rec, "--json").stdout
    assert json.loads(raw)["body"] == unseen and raw.isascii()
    described = p.aew("record", "body", "--help").stdout
    assert "Invisible" in described and "--json shows every one of" in " ".join(described.split())


def test_a_carriage_return_cannot_overwrite_the_line_a_reader_just_read(tmp_path):
    """A work unit's body is given as a file, which may hold a lone carriage return: a terminal would print what
    follows it over the start of the line."""
    p = sample_project(tmp_path)
    objective = tmp_path / "objective.md"
    objective.write_bytes(b"rejected by review\rAPPROVED          \nnext line\n")
    wid = create_unit(p, "ticket", "Overwritten", extra=("--scope", "calc/**", "--body-file", str(objective)))
    assert p.ok("record", "body", wid, "--json")["body"] == "rejected by review\rAPPROVED          \nnext line\n"
    assert body_of(p, wid) == "rejected by review\\u000dAPPROVED          \nnext line\n"


def test_the_read_takes_no_credential_and_changes_nothing(tmp_path):
    p = sample_project(tmp_path)
    _, _, rec = submitted(p, tmp_path)
    before = p.rev()
    res = p.aew("record", "body", rec, env={"AEW_LEAD_TOKEN": ""})
    assert res.returncode == 0 and res.stdout == DOCUMENT and p.rev() == before
    assert p.aew("record", "body", rec, "--expect-rev", str(before)).returncode == 2  # no such option
