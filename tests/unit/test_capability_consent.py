"""The operator's consent to download a tool (the operator's decision of 2026-11-05; the designer's rulings, STG-15).

AEW downloads no tool unless the operator chooses it, at one screen whoever asks (`aew init`, the Lead's start, `aew
capability fetch`); a "no" is remembered per tool and pin and stays visible; a missing tool is logged, not voided; and
a worker's launch never asks or downloads. Every check has its planted controls: the right case, the wrong case and
the missing one. The providers are the register's stand-in (``capability_stand_in``), one needed and one optional, and
every download comes from a local server or a stand-in function: nothing reaches the network.
"""

from __future__ import annotations

import http.server
import io
import json
import os
import sys
import threading
import urllib.request
from typing import Any

import pytest
from capability_stand_in import KEY, SOURCE, _archive, _record, make_register
from conftest import IS_WINDOWS

from aew import errors, process_kind
from aew.capability import consent, ops, records, status, store
from aew.capability import payload as P
from aew.engine.custody_ops import LEAD_SESSION_VARS, kept_out_refusal

URLOPEN = urllib.request.urlopen  # the real one: `make_register` replaces it with one that fails the test
DEGRADES = "the fake search fails without it"


@pytest.fixture
def reg(tmp_path, monkeypatch):
    """The stand-in, needed, and a second optional provider with its own name and the same payload."""
    out = make_register(tmp_path, monkeypatch)
    fake = {**out["shipped"]["fake"], "needed": True, "degrades": DEGRADES, "description": "a fake search"}
    extra = {**out["shipped"]["fake"], "command": "extra", "description": "an optional extra",
             "capabilities": ["FAKE_EXTRA"]}
    shipped = {"fake": fake, "extra": extra}
    monkeypatch.setattr(records, "shipped", lambda: shipped)
    out["shipped"] = shipped
    out["fetched"] = []
    return out


@pytest.fixture
def served(reg, monkeypatch):
    """Downloads answered from memory, counted: what a test's fetch brings."""

    def fetch(pinned: dict[str, Any]) -> bytes:
        reg["fetched"].append(pinned["source"])
        return reg["archive"]

    monkeypatch.setattr(P, "fetch", fetch)
    return reg


class Terminal:
    """The operator's terminal, scripted: each prompt shown, and the next answer typed."""

    def __init__(self, *answers: str | BaseException) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError(f"asked with no answer scripted: {prompt}")
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


@pytest.fixture
def terminal(monkeypatch):
    """The operator at a terminal: replace ``consent.read_terminal`` with a scripted :class:`Terminal`."""
    monkeypatch.setattr(consent, "terminal", lambda: True)

    def at(*answers: str | BaseException) -> Terminal:
        term = Terminal(*answers)
        monkeypatch.setattr(consent, "read_terminal", term)
        return term

    return at


def _installed(name: str = "fake") -> bool:
    record = records.shipped()[name]
    return P.path_of(name, record["command"], record["payloads"][KEY]).exists()


# ---------------------------------------------------------------------------------------------- needed, on the record


def test_ripgrep_is_needed_and_says_what_degrades_without_it():
    rg = records.shipped()["ripgrep"]
    assert records.needed(rg) is True and "OpenCode's search" in rg["degrades"]


@pytest.mark.parametrize("fields, refused", [
    ({"needed": True, "degrades": "its search"}, False),  # right: needed, with what degrades
    ({"needed": True}, True),  # wrong: needed, with nothing said of what degrades
    ({}, False),  # missing: optional by default
])
def test_a_needed_record_states_what_degrades_or_it_is_refused(reg, fields, refused):
    record = _record(reg["body"], reg["archive"], **fields)
    doc = {"schema": records.SCHEMA, "providers": {"fake": record}}
    if refused:
        with pytest.raises(errors.ValidationFailed) as exc:
            records.validate(doc, source="t")
        assert "`degrades`" in exc.value.message
    else:
        records.validate(doc, source="t")
        assert records.needed(record) is bool(fields.get("needed"))


def test_the_operators_record_overrides_needed(reg):
    """CAPR-04's two layers: the operator's record of the same name decides, here that the tool is optional."""
    mine = {k: v for k, v in reg["shipped"]["fake"].items() if k not in ("needed", "degrades")}
    with store.locked():
        state = store.read()
        state["operator_records"]["fake"] = {"record": mine, "added_at": "t", "base_digest": None, "base_record": None}
        store.write(state)
    assert [o.needed for o in consent.offers() if o.provider == "fake"] == [False]


# ---------------------------------------------------------------------------------------------- the screen


def test_the_screen_lists_needed_tools_in_full_and_optional_ones_as_a_count(reg):
    text = consent.screen(consent.offers())
    fake = next(line for line in text.splitlines() if line.startswith("  fake"))
    size = reg["shipped"]["fake"]["payloads"][KEY]["archive_size"]
    for part in ("fake 1.0", "`fake`", "a fake search", SOURCE, f"without it, {DEGRADES}"):
        assert part in fake, (part, fake)
    assert consent._size(size) in fake
    assert "extra" not in text and "Optional enhancements: 1 (type `pick` to see them)." in text
    assert "Enter downloads the needed ones: fake (" in text and "from example.invalid." in text
    assert "aew capability import" in text and "Choose needed / all / pick / none" in text


def test_with_nothing_needed_missing_the_screen_says_enter_downloads_nothing(reg):
    optional = [o for o in consent.offers() if not o.needed]
    text = consent.screen(optional)
    assert "Enter downloads nothing." in text and "Enter downloads the needed" not in text


@pytest.mark.parametrize("answers, chosen, declined", [
    ([""], ["fake"], ["extra"]),  # Enter: the needed ones, which the screen named
    (["needed"], ["fake"], ["extra"]),
    (["all"], ["fake", "extra"], []),
    (["none"], [], ["fake", "extra"]),
    (["pick", "2"], ["extra"], ["fake"]),
    (["pick", "fake extra"], ["fake", "extra"], []),
    (["yes please", "NONE"], [], ["fake", "extra"]),  # an answer that is no choice asks again
])
def test_each_answer_chooses_what_it_says_and_declines_the_rest(reg, answers, chosen, declined):
    decision = consent.ask(consent.offers(), Terminal(*answers))
    assert decision.answered is True
    assert [o.provider for o in decision.chosen] == chosen and [o.provider for o in decision.declined] == declined


def test_enter_with_nothing_needed_missing_takes_none(reg):
    optional = [o for o in consent.offers() if not o.needed]
    decision = consent.ask(optional, Terminal(""))
    assert decision.chosen == () and [o.provider for o in decision.declined] == ["extra"]


@pytest.mark.parametrize("ending", [errors.PermissionDenied("operator authorization timed out"), EOFError(), None])
def test_a_prompt_that_ends_unanswered_downloads_nothing_and_declines_nothing(reg, ending):
    """No timed default: a prompt that times out, or a terminal that closes, chooses nothing and records no "no"; so
    do three answers that are none of the choices."""
    term = Terminal(*([ending] if ending is not None else ["maybe", "perhaps", "later"]))
    decision = consent.ask(consent.offers(), term)
    assert decision.answered is False and decision.chosen == () and decision.declined == ()


# ---------------------------------------------------------------------------------------------- `aew init`


def test_init_asks_at_a_terminal_downloads_the_choice_and_remembers_the_no(served, terminal):
    term = terminal("")  # Enter: the needed one
    out = consent.at_init(None)
    assert len(term.prompts) == 1 and served["fetched"] == [SOURCE] and _installed("fake")
    assert [d["tool"] for d in out["declined"]] == ["extra"] and [m["tool"] for m in out["missing"]] == ["extra"]
    assert any(line.startswith("downloaded ") for line in out["downloaded"]["fake"])
    no = store.read()["declined"][f"extra:{KEY}"]
    assert no["sha256"] == served["shipped"]["extra"]["payloads"][KEY]["sha256"] and no["at"]


def test_init_does_not_ask_again_for_a_tool_declined_and_its_next_lists_it(served, terminal):
    terminal("none")
    consent.at_init(None)
    term = terminal()  # any prompt now fails the test
    out = consent.at_init(None)
    assert term.prompts == [] and served["fetched"] == []
    keys = consent.init_keys("acquire Lead authority", out)
    assert "you declined fake 1.0 at" in keys["next"] and "`aew capability fetch fake` downloads it" in keys["next"]
    assert f"(needed: without it, {DEGRADES})" in keys["next"] and "you declined extra 1.0 at" in keys["next"]
    assert keys["tools"] is out


def test_off_a_terminal_enter_is_never_a_default_and_nothing_downloads(served, monkeypatch):
    """Enter with no screen: a process without a terminal whose stdin holds a newline downloads nothing, records no
    "no", and says what is missing and how to get it."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
    out = consent.at_init(None)
    assert served["fetched"] == [] and not _installed() and not store.read()["declined"]
    assert [m["tool"] for m in out["missing"]] == ["fake", "extra"]
    assert consent.init_keys("next", out)["next"] == "next"  # nothing declined: `next` is what it always was
    with pytest.raises(errors.UsageError) as exc:
        consent.at_fetch([])
    assert exc.value.details["reason"] == "no_terminal" and served["fetched"] == []


def test_init_with_fetch_tool_downloads_what_it_names_with_no_screen(served):
    out = consent.at_init(["extra"])
    assert served["fetched"] == [SOURCE] and _installed("extra") and not _installed("fake")
    assert [m["tool"] for m in out["missing"]] == ["fake"]
    with pytest.raises(errors.NotFound):
        consent.check_names(["nonesuch"])  # refused before `aew init` writes anything


def test_init_never_downloads_in_a_lead_session_or_an_agents_own_aew(served, terminal, monkeypatch):
    term = terminal()
    monkeypatch.setenv(LEAD_SESSION_VARS[0], "x")
    out = consent.at_init(["fake"])
    assert served["fetched"] == [] and term.prompts == [] and [m["tool"] for m in out["missing"]] == ["fake", "extra"]
    monkeypatch.delenv(LEAD_SESSION_VARS[0])
    with process_kind.declared_as("aew (worker run)"):
        consent.at_init(["fake"])
    assert served["fetched"] == [] and term.prompts == []


# ---------------------------------------------------------------------------------------------- the Lead's start


def test_the_lead_start_asks_when_a_needed_tool_is_missing_and_not_declined(served, terminal):
    term = terminal("none")
    said = consent.at_lead_start(io.StringIO())
    assert len(term.prompts) == 1 and served["fetched"] == []
    assert said == [f"aew opencode: attention: fake, which the harness needs (without it, {DEGRADES}), is missing: "
                    f"you declined it at {store.read()['declined'][f'fake:{KEY}']['at']}. The Lead goes on without "
                    "it. `aew capability fetch fake` downloads it."]


def test_a_declined_needed_tool_gets_one_line_on_every_start_and_no_second_ask(served, terminal):
    terminal("none")
    consent.at_lead_start(io.StringIO())
    for _ in range(2):
        term = terminal()  # any prompt fails the test
        out = io.StringIO()
        said = consent.at_lead_start(out)
        assert term.prompts == [] and len(said) == 1 and "you declined it at" in said[0]
        assert out.getvalue() == said[0] + "\n"


def test_an_optional_tool_missing_says_nothing_at_the_lead_start(served, terminal):
    consent.at_init(["fake"])
    term = terminal()
    assert consent.at_lead_start(io.StringIO()) == [] and term.prompts == []


def test_a_lead_that_binds_no_tools_never_asks_and_still_names_a_missing_needed_tool(served, terminal):
    """Where the Lead is not contained (Windows), AEW binds no tools into it: nothing is asked, and a needed tool
    missing still gets its line, so it is logged, not voided."""
    term = terminal()
    said = consent.at_lead_start(io.StringIO(), asking=False)
    assert term.prompts == [] and served["fetched"] == [] and len(said) == 1
    assert "fake, which a contained run needs, is missing: it is not on this host" in said[0]
    assert "`aew capability fetch fake` downloads it" in said[0]


def test_off_a_terminal_the_lead_start_neither_asks_nor_says_and_the_record_keeps_it(served):
    out = io.StringIO()
    assert consent.at_lead_start(out) == [] and out.getvalue() == "" and served["fetched"] == []
    assert [o.provider for o in consent.offers() if o.needed] == ["fake"]  # still missing, still in the status


def test_at_a_terminal_a_needed_tool_the_download_did_not_bring_gets_its_line(reg, terminal, monkeypatch):
    def down(pinned: dict[str, Any]) -> bytes:
        raise errors.Unavailable("x", reason="fetch_failed", fetch_reason="unreachable")

    monkeypatch.setattr(P, "fetch", down)
    terminal("")
    said = consent.at_lead_start(io.StringIO())
    assert any("found no route" in line and "aew capability import" in line for line in said), said
    assert said[-1].startswith("aew opencode: attention: fake") and "it is not on this host" in said[-1]


def test_a_new_pin_asks_again(served, terminal, monkeypatch):
    terminal("none")
    consent.at_lead_start(io.StringIO())
    body = served["body"] + (b"\0" if IS_WINDOWS else b"\n")
    repinned = {**served["shipped"]["fake"], **{k: v for k, v in _record(body, _archive(body, "fake-1.0/fake.exe"
                if IS_WINDOWS else "fake-1.0/fake")).items() if k == "payloads"}}
    monkeypatch.setattr(records, "shipped", lambda: {**served["shipped"], "fake": repinned})
    term = terminal("none")
    consent.at_lead_start(io.StringIO())
    assert len(term.prompts) == 1  # the "no" was to the old pin


# ---------------------------------------------------------------------------------------------- declines stay visible


def test_a_declined_tool_reads_declined_in_its_status_the_doctor_and_a_runs_flag(served, terminal, monkeypatch,
                                                                                capsys):
    from aew import doctor

    terminal("none")
    consent.at_init(None)
    at = store.read()["declined"][f"fake:{KEY}"]["at"]
    copy = ops.listing()["providers"][[p["name"] for p in ops.listing()["providers"]].index("fake")]["aew_copy"]
    assert copy["reason"] == "declined" and f"declined to download it at {at}" in copy["cause"]
    row = next(c for c in doctor.environment_checks() if c["check"] == "capability:FAKE_SEARCH")
    assert row["status"] == "WARN" and f"declined to download it at {at}" in row["detail"]
    assert "`aew capability fetch fake` downloads it" in row["detail"]
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    flags = ops.flag_missing({"fake": {"command": "fake", "served": None, "tried": []}})
    assert [f["reason"] for f in flags] == ["declined"]
    assert "the operator declined to download it" in capsys.readouterr().err
    assert ops.run_record(flags)["reasons"] == {"fake": "declined"}  # logged, never voided


def test_a_download_the_operator_chose_clears_the_no(served, terminal):
    terminal("none")
    consent.at_init(None)
    consent.at_fetch(["fake"])
    assert _installed("fake") and f"fake:{KEY}" not in store.read()["declined"]


def test_check_never_downloads_a_declined_tool_and_says_how(served, terminal):
    terminal("none")
    consent.at_init(None)
    out = ops.check("fake")
    assert served["fetched"] == [] and "the operator declined it at" in " ".join(out["checked"]["fake"])


# ---------------------------------------------------------------------------------------------- the download


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True


def _serve(body: bytes, *, cut: bool = False, during: Any = None) -> tuple[str, Any]:
    """A local server that answers every GET with ``body``: ``cut`` sends half and closes; ``during`` runs before the
    body is sent."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
            if during is not None:
                during()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body[: len(body) // 2] if cut else body)
            if cut:
                self.wfile.flush()
                self.close_connection = True

        def log_message(self, *_a: Any) -> None:
            pass

    server = _Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/fake-1.0.tar.gz", server


@pytest.fixture
def local(reg, monkeypatch):
    """The record's source answered by a local server: ``local(body, **how)`` starts one."""
    servers = []

    def start(body: bytes, **how: Any) -> None:
        url, server = _serve(body, **how)
        servers.append(server)
        monkeypatch.setattr("urllib.request.urlopen", lambda _source, timeout=None: URLOPEN(url, timeout=timeout))

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _leftovers() -> list[str]:
    payloads = store.root() / store.PAYLOADS
    return sorted(str(p.relative_to(payloads)) for p in payloads.rglob("*")) if payloads.exists() else []


def test_a_download_matching_its_pin_is_placed(reg, local):
    local(reg["archive"])
    out = consent.at_fetch(["fake"])
    assert _installed("fake") and any(line.startswith("downloaded ") for line in out["downloaded"]["fake"])


def _same_size_other_archive(reg: dict[str, Any]) -> bytes:
    """A well-formed archive of another executable, the pinned archive's exact size: only the digests can refuse it."""
    from capability_stand_in import MEMBER

    size = len(reg["archive"])
    for at in range(len(reg["body"])):
        body = bytearray(reg["body"])
        body[at] ^= 0x01
        archive = _archive(bytes(body), MEMBER)
        if len(archive) == size:
            return archive
    raise AssertionError("no same-size archive found")


@pytest.mark.parametrize("which", ["another executable, well formed", "one byte of the archive changed"])
def test_a_download_off_its_pin_is_refused_and_nothing_is_placed(reg, local, which):
    """The hash check: an archive the pinned size that is not the pinned one, whether a well-formed archive of
    another executable or the pinned archive with one byte changed. Refused with its reason, and no file is left."""
    if which.startswith("another"):
        wrong = _same_size_other_archive(reg)
    else:
        wrong = bytearray(reg["archive"])
        wrong[len(wrong) // 2] ^= 0x01
    local(bytes(wrong))
    out = consent.at_fetch(["fake"])
    assert not _installed("fake") and _leftovers() == []
    assert "does not match its pin" in " ".join(out["downloaded"]["fake"]) or "cannot be read" in " ".join(
        out["downloaded"]["fake"])
    assert store.read()["refused"][f"fake:{KEY}"]["sha256"] == reg["shipped"]["fake"]["payloads"][KEY]["sha256"]


def test_a_download_cut_short_is_discarded_and_the_next_one_starts_clean(reg, local):
    local(reg["archive"], cut=True)
    consent.at_fetch(["fake"])
    assert not _installed("fake") and _leftovers() == []
    state = store.read()  # half an archive: a failed read, or one short of its pin, as the transport ends it
    assert f"fake:{KEY}" in state["fetch_failures"] or "does not match its pin" in state["refused"][f"fake:{KEY}"][
        "reason"], state
    local(reg["archive"])
    consent.at_fetch(["fake"])
    assert _installed("fake")


def test_the_registers_lock_is_never_held_across_the_download(reg, local, monkeypatch):
    """The designer's ruling (STG-15): a download runs with no lock held. While the server is sending, another
    register command takes the lock at once."""
    monkeypatch.setattr(store, "RECORD_WAIT_S", 1.0)
    took: list[bool] = []

    def another_command() -> None:
        try:
            with store.locked(short=True):
                took.append(True)
        except errors.AEWError:
            took.append(False)

    local(reg["archive"], during=another_command)
    consent.at_fetch(["fake"])
    assert took == [True] and _installed("fake")


def test_an_approved_add_downloads_with_no_lock_held_either(reg, local, monkeypatch):
    """The same rule for `aew capability add` (applied at the operator endpoint once approved): its payload is
    downloaded before the register's lock is taken, and installed under it."""
    from capability_stand_in import _principal

    monkeypatch.setattr(store, "RECORD_WAIT_S", 1.0)
    took: list[bool] = []

    def another_command() -> None:
        try:
            with store.locked(short=True):
                took.append(True)
        except errors.AEWError:
            took.append(False)

    local(reg["archive"], during=another_command)
    record = {**reg["shipped"]["extra"], "description": "the operator's own"}
    text = json.dumps({"schema": records.SCHEMA, "providers": {"mine": record}})
    out = ops.apply(_principal(), ops.preview(ops.ADD, {"text": text, "source": "test"}))
    assert took == [True] and out["added"] == ["mine"]


def test_offline_the_report_names_the_offline_import(reg, monkeypatch):
    def unreachable(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.URLError(OSError("no route"))

    import urllib.error

    monkeypatch.setattr("urllib.request.urlopen", unreachable)
    out = consent.at_fetch(["fake"])
    assert "aew capability import" in out["offline"] and not _installed("fake")


# ---------------------------------------------------------------------------------------------- who may fetch


def test_capability_fetch_is_refused_in_a_lead_session_and_in_an_agents_own_aew(served, monkeypatch):
    from aew.cli.capability_commands import refuse_lead_session

    monkeypatch.setenv(LEAD_SESSION_VARS[0], "x")
    with pytest.raises(errors.PermissionDenied) as exc:
        refuse_lead_session("fetch")
    assert "`aew capability fetch` is the operator's" in exc.value.message
    with pytest.raises(errors.PermissionDenied):
        consent.at_fetch(["fake"])
    monkeypatch.delenv(LEAD_SESSION_VARS[0])
    with process_kind.declared_as("aew (worker run)"):
        with pytest.raises(errors.PermissionDenied) as exc:
            ops.refuse_an_agents_own("fetch")
        assert exc.value.details["reason"] == "operator_only"
        with pytest.raises(errors.PermissionDenied):
            consent.at_fetch(["fake"])
    assert served["fetched"] == []
    refusal = kept_out_refusal(frozenset({"capability", "fetch"}))  # the broker's channels say the same
    assert refusal is not None and "`aew capability fetch` is the operator's" in refusal


def test_capability_fetch_through_the_cli_downloads_what_it_names(served, capsys):
    from aew.cli.main import main

    assert main(["capability", "fetch", "fake", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert any(line.startswith("downloaded ") for line in out["downloaded"]["fake"]) and _installed("fake")


# ---------------------------------------------------------------------------------------------- logged, not voided


@pytest.mark.parametrize("tools, said", [
    (["rg"], True),  # right: the run went without it, and is told so
    ([], False),  # missing: nothing to say
    (None, False),
])
def test_the_agent_is_told_the_tools_its_run_goes_without_as_it_is_told_its_missing_skills(tools, said):
    """The operator's condition (2026-11-05): a missing tool acts as a missing skill does. The system text names the
    tools the run has no copy of, and says to proceed without them and say so in the report."""
    from test_opencode_units import contract

    from aew.harness.opencode import projection

    system = projection.invocation_config(contract(), unavailable_tools=tools)["agents"][projection.AGENT]["system"]
    line = next((x for x in system.splitlines() if x.startswith("- Tools AEW brings")), None)
    assert (line is not None) is said, system
    if said:
        assert line == ("- Tools AEW brings that this run does not have: `rg`, so what runs them fails here (search "
                        "with `grep -rn` or `find` instead). Proceed without them and say so in your report.")
    skills = next(x for x in system.splitlines() if x.startswith("- Skills"))
    assert "Proceed without them and say so in your report." in skills  # the same words as its skills line


def test_unavailable_reads_the_runs_record_stubs_only():
    record = ops.run_record([{"tool": "rg", "provider": "ripgrep", "served": "stub", "reason": "declined"},
                             {"tool": "jq", "provider": "jq", "served": "host", "reason": "not_installed"}])
    assert ops.unavailable(record) == ["rg"]  # right: a stub; the host copy still runs
    assert ops.unavailable(None) == [] and ops.unavailable({}) == []  # missing
    assert ops.unavailable({"detail": "not a list"}) == []  # wrong shape


@pytest.mark.parametrize("served", ["host", None])
def test_a_launchs_attention_line_names_the_download_route_never_check(reg, monkeypatch, capsys, served):
    """As a contained Lead's start printed it with the host's unpinned rg: the fix names `aew capability fetch <tool>`
    online and `aew capability import` offline, from the status's one owner (``status.fetch_fix``), never `aew
    capability check`, which downloads only a tool it names."""
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    tool = {"command": "fake", "served": status.HOST_COPY if served else None, "path": "/usr/bin/fake", "tried": []}
    ops.flag_missing({"fake": tool})
    fix = capsys.readouterr().err.split("Fix:")[1]
    assert fix.strip() == (f"{status.fetch_fix('fake')}.") and "aew capability check" not in fix
    assert "`aew capability fetch fake` downloads it (online)" in fix and "`aew capability import`" in fix


def test_a_worker_launchs_flag_never_asks_or_downloads(served, terminal, monkeypatch):
    """A worker's launch never asks and never downloads (the designer's ruling): its flag, at a terminal, with a
    needed tool missing and not declined, prints its line and nothing more."""
    term = terminal()
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    flags = ops.flag_missing({"fake": {"command": "fake", "served": None, "tried": []}})
    assert [f["reason"] for f in flags] == ["not_installed"] and term.prompts == [] and served["fetched"] == []


@pytest.mark.skipif(IS_WINDOWS, reason="a pseudo-terminal is POSIX's")
def test_the_screen_on_a_pseudo_terminal_takes_a_typed_answer(reg, tmp_path):
    """The prompt driven as the operator drives it: a child on a pseudo-terminal of its own, its controlling terminal,
    reading the answer typed there and never stdin."""
    import pty
    import select

    script = tmp_path / "child.py"
    script.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "from aew.capability import consent, records, store\n"
        f"store.ROOT_OVERRIDE = Path({str(reg['root'])!r})\n"
        f"shipped = json.loads({json.dumps(json.dumps(reg['shipped']))})\n"
        "records.shipped = lambda: shipped\n"
        "out = consent.at_fetch([])\n"
        "print('RESULT ' + json.dumps(out['declined']))\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    pid, fd = pty.fork()
    if pid == 0:  # the child: its controlling terminal is the pseudo-terminal
        os.execve(sys.executable, [sys.executable, "-B", str(script)], env)  # noqa: S606 (argv is fixed here)
    seen = b""
    try:
        while b"Choose needed / all / pick / none" not in seen:
            ready, _, _ = select.select([fd], [], [], 60)
            assert ready, seen
            try:
                seen += os.read(fd, 4096)
            except OSError:  # the child ended before its screen: what it printed says why
                raise AssertionError(seen.decode(errors="replace")) from None
        os.write(fd, b"none\r")
        while b"RESULT" not in seen or not seen.rstrip().endswith(b"]"):
            ready, _, _ = select.select([fd], [], [], 60)
            assert ready, seen
            try:
                seen += os.read(fd, 4096)
            except OSError:
                break
    finally:
        os.waitpid(pid, 0)
    declined = json.loads(seen.split(b"RESULT ", 1)[1].splitlines()[0])
    assert [d["tool"] for d in declined] == ["fake", "extra"]
    assert f"fake:{KEY}" in store.read()["declined"]
