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
from types import SimpleNamespace
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
    monkeypatch.setattr(consent, "binds_here", lambda: True)  # a host whose contained runs get AEW's tools bound
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


def test_where_aew_places_no_tools_none_is_needed_and_the_screen_says_so_once(reg, monkeypatch):
    """Review of #343, m3: on a host with no contained context (Windows), OpenCode's own lookup serves, so ripgrep is
    not called needed, Enter downloads nothing, and the screen says once why."""
    monkeypatch.setattr(consent, "binds_here", lambda: False)
    shown = consent.offers()
    assert [o.needed for o in shown] == [False, False]
    text = consent.screen(shown)
    assert text.count(consent.NOT_PLACED[1:]) == 1 and "Needed" not in text and "Enter downloads nothing." in text


def test_where_the_hosts_copy_serves_the_screen_says_so_never_that_none_is_here(reg, monkeypatch):
    """Review of #343, m3: with host copies on and the host's own copy on PATH, the screen names it as what serves
    meanwhile, never "none is on this host"."""
    from capability_stand_in import _plant_host_copy

    host = _plant_host_copy(reg, monkeypatch)
    fake = next(o for o in consent.offers() if o.provider == "fake")
    assert fake.host == str(host)
    text = consent.screen(consent.offers())
    assert f"meanwhile the host's unpinned copy at {host} serves" in text and "None is on this host" not in text
    assert f"without it, {DEGRADES}" not in text


def test_with_nothing_needed_missing_the_screen_says_enter_downloads_nothing(reg):
    optional = [o for o in consent.offers() if not o.needed]
    text = consent.screen(optional)
    assert "Enter downloads nothing." in text and "Enter downloads the needed" not in text


@pytest.mark.parametrize("answers, chosen, declined", [
    ([""], ["fake"], []),  # Enter: the needed ones, which the screen named; the optional one is no "no"
    (["needed"], ["fake"], []),
    (["all"], ["fake", "extra"], []),
    (["none"], [], ["fake"]),  # only the tool listed in full is declined (review of #343, m2)
    (["pick", "2"], ["extra"], ["fake"]),
    (["pick", "fake extra"], ["fake", "extra"], []),
    (["pick", ""], [], []),  # Enter at the pick: nothing named, so nothing downloaded and nothing declined
    (["yes please", "NONE"], [], ["fake"]),  # an answer that is no choice asks again
])
def test_each_answer_chooses_what_it_says_and_declines_only_what_was_listed_in_full(reg, answers, chosen, declined):
    decision = consent.ask(consent.offers(), Terminal(*answers))
    assert decision.answered is True
    assert [o.provider for o in decision.chosen] == chosen and [o.provider for o in decision.declined] == declined


def test_enter_with_nothing_needed_missing_takes_none_and_declines_none(reg):
    optional = [o for o in consent.offers() if not o.needed]
    decision = consent.ask(optional, Terminal(""))
    assert decision.chosen == () and decision.declined == ()


def test_the_re_prompt_repeats_what_enter_downloads(reg):
    """Review of #343, n5."""
    term = Terminal("maybe", "none")
    consent.ask(consent.offers(), term)
    assert consent.enter_line(consent.offers()) in term.prompts[1] and "is not one of" in term.prompts[1]


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
    assert out["declined"] == [] and [m["provider"] for m in out["missing"]] == ["extra"]
    assert any(line.startswith("downloaded ") for line in out["downloaded"]["fake"])
    assert store.read()["declined"] == {}  # the optional tool, shown as a count, is no "no" (review of #343, m2)


def test_a_none_at_init_records_the_no_for_its_pin(served, terminal):
    terminal("none")
    consent.at_init(None)
    no = store.read()["declined"]
    assert list(no) == [f"fake:{KEY}"] and no[f"fake:{KEY}"]["at"]
    assert no[f"fake:{KEY}"]["sha256"] == served["shipped"]["fake"]["payloads"][KEY]["sha256"]


def test_init_does_not_ask_again_for_a_tool_declined_and_its_next_lists_it(served, terminal):
    terminal("none")
    consent.at_init(None)
    term = terminal("none")  # the optional tool is asked again; the declined one is not on the screen
    out = consent.at_init(None)
    assert len(term.prompts) == 1 and "  fake 1.0" not in term.prompts[0] and served["fetched"] == []
    keys = consent.init_keys("acquire Lead authority", out)
    assert "you declined fake 1.0 at" in keys["next"] and "`aew capability fetch fake` downloads it" in keys["next"]
    assert f"(needed: without it, {DEGRADES})" in keys["next"] and "extra" not in keys["next"]
    assert keys["tools"] is out


def test_off_a_terminal_enter_is_never_a_default_and_nothing_downloads(served, monkeypatch):
    """Enter with no screen: a process without a terminal whose stdin holds a newline downloads nothing, records no
    "no", and says what is missing and how to get it."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
    out = consent.at_init(None)
    assert served["fetched"] == [] and not _installed() and not store.read()["declined"]
    assert [m["provider"] for m in out["missing"]] == ["fake", "extra"]
    assert consent.init_keys("next", out)["next"] == "next"  # nothing declined: `next` is what it always was
    with pytest.raises(errors.UsageError) as exc:
        consent.at_fetch([])
    assert exc.value.details["reason"] == "no_terminal" and served["fetched"] == []


def test_init_with_fetch_tool_downloads_what_it_names_with_no_screen(served):
    out = consent.at_init(["extra"])
    assert served["fetched"] == [SOURCE] and _installed("extra") and not _installed("fake")
    assert [m["provider"] for m in out["missing"]] == ["fake"]
    with pytest.raises(errors.NotFound):
        consent.check_names(["nonesuch"])  # refused before `aew init` writes anything


def test_init_fetch_none_leaves_every_tool_unanswered_at_a_terminal(served, terminal):
    term = terminal("all")
    consent.check_names(["none"])
    out = consent.at_init(["none"])
    assert term.prompts == [] and served["fetched"] == []
    assert not _installed() and not store.read()["declined"]
    assert out["answer"] is None and out["downloaded"] == {} and out["declined"] == []
    assert [tool["provider"] for tool in out["missing"]] == ["fake", "extra"]


def test_init_never_downloads_in_a_lead_session_or_an_agents_own_aew(served, terminal, monkeypatch):
    term = terminal()
    monkeypatch.setenv(LEAD_SESSION_VARS[0], "x")
    out = consent.at_init(["fake"])
    assert served["fetched"] == [] and term.prompts == []
    assert [m["provider"] for m in out["missing"]] == ["fake", "extra"]
    monkeypatch.delenv(LEAD_SESSION_VARS[0])
    with process_kind.declared_as("aew (worker run)"):
        consent.at_init(["fake"])
    assert served["fetched"] == [] and term.prompts == []


# ---------------------------------------------------------------------------------------------- the Lead's start


def _flag_seen(monkeypatch: Any) -> None:
    """The launch's own flag, shown once on the operator's terminal, as the contained Lead's sandbox shows it."""
    monkeypatch.setattr(ops, "_to_terminal", lambda: True)
    ops.flag_missing({"fake": {"command": "fake", "served": None, "path": None, "tried": []}})


def test_the_lead_start_asks_when_a_needed_tool_is_missing_and_not_declined(served, terminal):
    term = terminal("none")
    said = consent.at_lead_start(io.StringIO())
    assert len(term.prompts) == 1 and served["fetched"] == []
    assert said == []  # the launch's own flag names it this time (review of #343, n6)


def test_a_tool_is_named_once_at_a_start_by_the_flag_or_by_the_start_never_both(served, terminal, monkeypatch,
                                                                               capsys):
    """Review of #343, n6: the start's line stands down while the launch's flag is about to name the tool, and stands
    in on every later start, when the flag has already said it and stays quiet."""
    terminal("none")
    assert consent.at_lead_start(io.StringIO()) == []
    _flag_seen(monkeypatch)
    assert "the operator declined to download it" in capsys.readouterr().err
    said = consent.at_lead_start(io.StringIO())
    at = store.read()["declined"][f"fake:{KEY}"]["at"]
    assert said == [f"aew opencode: attention: AEW's pinned fake, which the harness needs, is missing: you declined "
                    f"it at {at}; the Lead goes on without it ({DEGRADES}). `aew capability fetch fake` downloads it."]
    _flag_seen(monkeypatch)
    assert capsys.readouterr().err == ""  # the flag says it once per state


def test_a_declined_needed_tool_gets_one_line_on_every_start_and_no_second_ask(served, terminal, monkeypatch):
    terminal("none")
    consent.at_lead_start(io.StringIO())
    _flag_seen(monkeypatch)
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


def test_a_lead_that_binds_no_tools_never_asks_and_says_once_why_none_is_placed(served, terminal, caplog):
    """Where the Lead is not contained (Windows), AEW binds no tools into it: nothing is asked, and a needed tool
    missing still gets its line, so it is logged, not voided."""
    term = terminal()
    with caplog.at_level("INFO", logger="aew.capability.consent"):
        said = consent.at_lead_start(io.StringIO(), asking=False)
    assert term.prompts == [] and served["fetched"] == [] and len(said) == 1
    assert said[0] == ("aew opencode: this Lead is not contained, so AEW places none of its tools in it and "
                       "OpenCode's own lookup serves (fake, extra: not AEW's pinned copy).")
    assert "needs" not in said[0] and "aew capability fetch" not in said[0]  # review of #343, m3
    assert said[0] in caplog.text  # logged, whether or not a terminal reads it


def test_off_a_terminal_the_lead_start_neither_asks_nor_says_and_the_record_keeps_it(served):
    out = io.StringIO()
    assert consent.at_lead_start(out) == [] and out.getvalue() == "" and served["fetched"] == []
    assert [o.provider for o in consent.offers() if o.needed] == ["fake"]  # still missing, still in the status


def test_at_a_terminal_a_download_that_found_no_route_names_the_offline_import(reg, terminal, monkeypatch):
    def down(pinned: dict[str, Any]) -> bytes:
        raise errors.Unavailable("x", reason="fetch_failed", fetch_reason="unreachable")

    monkeypatch.setattr(P, "fetch", down)
    terminal("")
    said = consent.at_lead_start(io.StringIO())
    assert any("found no route" in line and "aew capability import" in line for line in said), said
    assert not any("attention" in line for line in said)  # its new state is the launch's flag's to name (n6)


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


def test_a_no_to_a_new_pin_after_a_check_reads_declined_everywhere(served, terminal, monkeypatch):
    """Review of #343, m1: on a host that checked the old pin, a "no" to the new one reads declined in the status, so
    list, doctor, a launch's flag and the run's record say so, never pin_changed."""
    consent.at_fetch(["fake"])  # the old pin downloaded and checked
    assert store.read()["checks"]
    body = served["body"] + (b"\0" if IS_WINDOWS else b"\n")
    member = "fake-1.0/fake.exe" if IS_WINDOWS else "fake-1.0/fake"
    repinned = {**served["shipped"]["fake"], "payloads": _record(body, _archive(body, member))["payloads"]}
    monkeypatch.setattr(records, "shipped", lambda: {**served["shipped"], "fake": repinned})
    copy = next(p for p in ops.listing()["providers"] if p["name"] == "fake")["aew_copy"]
    assert copy["reason"] == "pin_changed"  # control: before the "no", the new pin reads as such
    terminal("none")
    consent.at_lead_start(io.StringIO())
    copy = next(p for p in ops.listing()["providers"] if p["name"] == "fake")["aew_copy"]
    assert copy["reason"] == "declined" and "declined to download it" in copy["cause"], copy


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


def test_a_pin_that_changes_during_the_download_installs_nothing(reg, local, monkeypatch):
    """Review of #343, m6: the record is re-read under the lock, and a pin changed while the archive was on the wire
    installs nothing, and says so."""
    body = reg["body"] + (b"\0" if IS_WINDOWS else b"\n")
    member = "fake-1.0/fake.exe" if IS_WINDOWS else "fake-1.0/fake"
    repinned = {**reg["shipped"]["fake"], "payloads": _record(body, _archive(body, member))["payloads"]}

    def repin() -> None:
        monkeypatch.setattr(records, "shipped", lambda: {**reg["shipped"], "fake": repinned})

    local(reg["archive"], during=repin)
    out = consent.get(consent.named(["fake"]))
    assert out["fake"] == ["its record or pin changed during the download, so nothing was installed"]
    assert _leftovers() == []


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


RG = {"command": "rg", "fallback": "`grep -rn` or `find`"}


@pytest.mark.parametrize("tools, said", [
    ([RG], "`rg`, so what runs them fails here (search with `grep -rn` or `find` instead)"),  # right
    ([{"command": "jq", "fallback": None}], "`jq`, so what runs them fails here."),  # no search: no fallback (n4)
    ([], None),  # missing: nothing to say
    (None, None),
])
def test_the_agent_is_told_the_tools_its_run_goes_without_as_it_is_told_its_missing_skills(tools, said):
    """The operator's condition (2026-11-05): a missing tool acts as a missing skill does. The system text names the
    tools the run has no copy of, and says to proceed without them and say so in the report."""
    from test_opencode_units import contract

    from aew.harness.opencode import projection

    # a card skill AEW does not ship, so the run has a missing skill's line to sit beside (E127's skills lines)
    planned = contract(skills=["not-shipped"])
    system = projection.invocation_config(planned, unavailable_tools=tools)["agents"][projection.AGENT]["system"]
    lines = system.splitlines()
    line = next((x for x in lines if x.startswith("- Tools AEW brings")), None)
    assert (line is not None) is (said is not None), system
    skills = next(x for x in lines if x.startswith("- Skills"))
    assert "Proceed without them and say so in your report." in skills  # the same words as its skills line
    if said:
        assert line == (f"- Tools AEW brings that this run does not have: {said}"
                        + ("" if said.endswith(".") else ".") + " Proceed without them and say so in your report.")
        assert lines.index(line) == lines.index(skills) + 1  # side by side: the skills lines, then the tools line


def test_the_adapters_launch_puts_the_runs_missing_tools_in_its_system_text(tmp_path, monkeypatch):
    """Review of #343, m7: what the supervisor sets from the run's record (``K.UNAVAILABLE_TOOLS``) reaches the
    system text the adapter's launch writes: planted at the launch, stopped right after the configuration is built."""
    from test_opencode_units import contract

    from aew.harness import contract as K
    from aew.harness.opencode import adapter, projection

    built: dict[str, Any] = {}

    class Built(Exception):
        pass

    real = projection.invocation_config

    def capture(c: Any, **kw: Any) -> Any:
        built["system"] = real(c, **kw)["agents"][projection.AGENT]["system"]
        raise Built

    monkeypatch.setattr(projection, "invocation_config", capture)
    tree = type("Tree", (), {"network": None})()
    for tools, said in (([RG], True), ([], False)):  # right, and missing
        c = contract()
        c.extra[K.UNAVAILABLE_TOOLS] = tools
        with pytest.raises(Built):
            adapter.OpenCodeAdapter(tree, tmp_path / f"run-{len(tools)}", lambda _e: None).launch(c, {})
        assert ("- Tools AEW brings that this run does not have: `rg`" in built["system"]) is said


def test_unavailable_reads_the_runs_record_stubs_only():
    record = ops.run_record([{"command": "rg", "provider": "ripgrep", "served": "stub", "reason": "declined"},
                             {"command": "jq", "provider": "jq", "served": "host", "reason": "not_installed"}])
    assert ops.unavailable(record) == [RG]  # right: a stub, with ripgrep's search fallback; the host copy still runs
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
    assert [d["provider"] for d in declined] == ["fake"]  # the optional one, shown as a count, is no "no" (m2)
    assert list(store.read()["declined"]) == [f"fake:{KEY}"]


# ---------------------------------------------------------------------------------------------- the tools a run has
# Card-capability resolution (the Lead's ruling, 2026-11-07): the pack splits the card's capabilities by whether a tool
# of AEW's serves them, from the card alone; a run's system text names the tools it has, by the names it calls them.

PURPOSES = {"ripgrep": ("rg", "exact code and text search"), "fd": ("fd", "find files by name or pattern"),
            "jq": ("jq", "query and transform JSON"), "yq": ("yq-go", "query and edit YAML"),
            "ast-grep": ("ast-grep", "structural code search by syntax-tree pattern"),
            "universal-ctags": ("uctags", "a symbol outline of source files")}


def _card_capabilities() -> set[str]:
    from aew import roles

    return {c for card in roles.builtin_cards().values()
            for c in [*card.meta.get("required_capabilities", []), *card.meta.get("optional_capabilities", [])]}


def test_the_card_capability_table_is_pinned_both_ways_to_the_cards_and_the_shipped_records():
    """Every row names a capability some shipped card asks for and capability IDs a shipped record serves; and every
    card capability whose name is a shipped capability ID's has a row, so a new card name a tool serves is not left
    unresolved."""
    cards = _card_capabilities()
    served = {c for r in records.shipped().values() for c in r["capabilities"]}
    for name, ids in records.CARD_CAPABILITIES.items():
        assert name in cards, name
        assert ids and set(ids) <= served, (name, ids)
    assert {c for c in cards if c.upper() in served} <= set(records.CARD_CAPABILITIES)
    # The rows a name match cannot find, as the Lead ruled them (2026-11-07): a dropped one is caught here
    assert records.CARD_CAPABILITIES["symbol_navigation"] == ("SYMBOL_OUTLINE",)
    assert records.CARD_CAPABILITIES["repository_exploration"] == ("FILE_FIND", "TEXT_SEARCH")


def test_each_shipped_tools_purpose_is_its_descriptions_first_clause():
    assert {n: (r["command"], records.purpose(r)) for n, r in records.shipped().items()} == PURPOSES
    assert records.purpose({"capabilities": ["FILE_FIND"]}) == "file find"  # no description: its capabilities


@pytest.mark.parametrize("required, optional, said", [
    (["exact_code_search", "build_execution"], ["symbol_navigation", "static_analysis"],
     ["Capabilities AEW's tools serve (your system text names the tools this run has): exact_code_search, "
      "symbol_navigation",
      "Capabilities no tool of AEW's serves (use your shell and the project's own commands): build_execution, "
      "static_analysis"]),
    (["repository_exploration"], [],
     ["Capabilities AEW's tools serve (your system text names the tools this run has): repository_exploration"]),
    (["documentation_lookup"], [],
     ["Capabilities no tool of AEW's serves (use your shell and the project's own commands): documentation_lookup"]),
    ([], [], ["Other capabilities requested: none"]),
    (["source_mutation"], [], ["Other capabilities requested: none"]),  # authority-sensitive: its own line
])
def test_the_pack_splits_a_cards_capabilities_by_whether_a_tool_serves_them(monkeypatch, required, optional, said):
    """The pending line is gone. The split is the card's alone, never this host's: with no shipped record at all the
    lines are the same, so a pack's hash never moves with what a host has."""
    from aew.knowledge import context as ctxmod

    card = {"display_name": "X", "role": "x", "extends": "implementer", "purpose": "p",
            "required_capabilities": required, "optional_capabilities": optional}
    inputs = ctxmod.PackInputs.__new__(ctxmod.PackInputs)
    object.__setattr__(inputs, "card", card)
    lines = ctxmod._card_section(inputs)
    assert not any("workbench resolution pending" in x for x in lines)
    start = next(i for i, x in enumerate(lines) if x.startswith("Authority-sensitive")) + 1
    end = next(i for i, x in enumerate(lines) if x.startswith("Expected outputs"))
    assert lines[start:end] == said
    monkeypatch.setattr(records, "shipped", lambda: {})
    assert ctxmod._card_section(inputs) == lines


def test_available_names_a_served_copy_by_the_command_its_bind_placed_and_its_purpose_from_the_register(reg):
    """Review of #353, m2: the name is the one the label records (``bind.settle``'s, the entry on the run's PATH),
    the purpose the register's; a provider whose command the register now names otherwise is not named at all."""
    fake = {"served": status.AEW_COPY, "command": "fake"}
    tools = {"fake": fake,  # right
             "absent": {"served": status.AEW_COPY, "command": "absent"},  # no such provider in force
             "stubbed": "not a dict"}
    assert ops.available(tools) == [{"command": "fake", "purpose": "fake search"}]
    assert ops.available({"fake": {**fake, "served": status.HOST_COPY}}) == [{"command": "fake",
                                                                              "purpose": "fake search"}]
    assert ops.available({"fake": {**fake, "command": "fake4"}}) == []  # wrong: placed under another command
    assert ops.available({"fake": {"served": status.AEW_COPY}}) == []  # missing: no command recorded
    assert ops.available({"fake": {**fake, "served": None}}) == []  # the stub, or no entry: missing, said elsewhere
    assert ops.available(None) == [] and ops.available({}) == []


def test_placed_reads_a_contained_labels_self_test_and_nothing_where_not_contained(reg):
    label = {"self_test": {"tools": {"fake": {"served": status.AEW_COPY, "command": "fake"}}}}
    assert ops.placed(label, contained=True) == {"placed": True, "tools": [{"command": "fake",
                                                                            "purpose": "fake search"}]}
    assert ops.placed(label, contained=False) == {"placed": False, "tools": []}
    assert ops.placed(None, contained=True) == {"placed": True, "tools": []}


ALL = {"placed": True, "tools": [{"command": c, "purpose": p} for c, p in PURPOSES.values()]}
NAMED = ("- Tools AEW placed for you, by the names to call them: `rg` (exact code and text search), `fd` (find files "
         "by name or pattern), `jq` (query and transform JSON), `yq-go` (query and edit YAML), `ast-grep` (structural "
         "code search by syntax-tree pattern), `uctags` (a symbol outline of source files).")


@pytest.mark.parametrize("available, said", [
    (ALL, [NAMED]),  # right
    ({"placed": False, "tools": []}, ["- AEW's tools are not placed in this run (it is not contained): use what the "
                                      "host provides."]),
    ({"placed": True, "tools": []}, []),  # contained, nothing served: its missing tools have their own line
    (None, []),  # nothing recorded
])
def test_the_tools_line_renders_exactly(available, said):
    from aew.harness.opencode import projection

    assert projection.tools_text(available) == said


def test_a_runs_system_text_names_its_tools_between_its_skills_and_what_it_goes_without(tmp_path, monkeypatch):
    """Through the adapter's launch, from what the supervisor sets (``K.AVAILABLE_TOOLS``): the skills lines, then the
    tools the run has, then the ones it has not."""
    from test_opencode_units import contract

    from aew.harness import contract as K
    from aew.harness.opencode import adapter, projection

    built: dict[str, Any] = {}

    class Built(Exception):
        pass

    real = projection.invocation_config

    def capture(c: Any, **kw: Any) -> Any:
        built["system"] = real(c, **kw)["agents"][projection.AGENT]["system"]
        raise Built

    monkeypatch.setattr(projection, "invocation_config", capture)
    tree = type("Tree", (), {"network": None})()
    c = contract(skills=["not-shipped"])
    c.extra[K.AVAILABLE_TOOLS] = {"placed": True, "tools": ALL["tools"][1:]}
    c.extra[K.UNAVAILABLE_TOOLS] = [RG]
    with pytest.raises(Built):
        adapter.OpenCodeAdapter(tree, tmp_path / "run", lambda _e: None).launch(c, {})
    lines = built["system"].splitlines()
    skills = next(i for i, x in enumerate(lines) if x.startswith("- Skills"))
    assert lines[skills + 1] == NAMED.replace("`rg` (exact code and text search), ", "")
    assert lines[skills + 2].startswith("- Tools AEW brings that this run does not have: `rg`")


def test_the_contained_leads_system_text_names_its_tools_and_that_its_shell_asks_first():
    """The Lead is told its tools as a worker is, and, from its own rules, that its shell asks the operator before
    any of them: only `aew` and git reads run without asking."""
    from aew.harness.opencode import projection

    system = projection.lead_config(tools=ALL)["agents"][projection.LEAD_AGENT]["system"]
    assert NAMED + projection.LEAD_TOOLS_NOTE in system.splitlines()
    assert "Tools AEW placed" not in projection.lead_config()["agents"][projection.LEAD_AGENT]["system"]
    shell = [r for r in projection.LEAD_RULES if r["action"] == "shell"]
    assert shell[0] == projection.rule("shell", "ask")  # every other command asks: what the note says
    assert [r["resource"] for r in shell if r["effect"] == "allow"] == ["aew *", *projection.LEAD_GIT_READS]


def test_the_leads_tools_note_names_the_tools_its_rules_let_it_use_without_asking():
    """Review of #353, m3: the note's "read, glob and grep" are the Lead's own rules' (one list for both), and for each
    the last rule that covers every path allows it, so the note never sends the Lead to a tool that asks."""
    from aew.harness.opencode import projection

    assert projection.LEAD_TOOLS_NOTE.endswith(" so search with your read, glob and grep tools first.")
    for action in projection.LEAD_FREE_TOOLS:
        last = [r for r in projection.LEAD_RULES if r["action"] in (action, "*") and r["resource"] == "*"][-1]
        assert last == projection.rule(action, "allow"), action


def test_the_supervisor_sets_what_a_run_is_told_of_its_tools_from_its_label_and_whether_it_is_contained(reg):
    """Review of #353, m1: the run's tools come from its own label, and a run with no layout (not contained) is told
    none are placed, whatever its label holds."""
    from aew.harness import contract as K
    from aew.harness import supervisor

    label = {"self_test": {"tools": {"fake": {"served": status.AEW_COPY, "command": "fake"}}},
             "missing_tools": ops.run_record([{"command": "extra", "provider": "extra", "served": "stub",
                                               "reason": "declined"}])}
    for layout, placed in ((object(), {"placed": True, "tools": [{"command": "fake", "purpose": "fake search"}]}),
                           (None, {"placed": False, "tools": []})):
        contract = SimpleNamespace(extra={})
        supervisor.Supervisor._tools(SimpleNamespace(record={"containment": label}, layout=layout), contract)
        assert contract.extra[K.AVAILABLE_TOOLS] == placed
        assert contract.extra[K.UNAVAILABLE_TOOLS] == [{"command": "extra", "fallback": None}]


def test_the_contained_leads_start_configures_it_with_the_tools_its_sandboxs_self_test_placed(reg, tmp_path,
                                                                                             monkeypatch):
    """Review of #353, m1: the contained Lead's own start, with its sandbox faked, gives its configuration the tools
    the sandbox's self-test settled, from its label."""
    from aew.harness import containment
    from aew.harness.opencode import lead, projection

    class Stop(Exception):
        pass

    seen: dict[str, Any] = {}

    def stop(*_: Any, **kw: Any) -> None:
        seen.update(kw)
        raise Stop

    monkeypatch.setattr(projection, "lead_config", stop)  # the step after: the launch goes no further
    monkeypatch.setattr(os, "isatty", lambda fd: fd == 0)  # an operator's terminal, as test_lead_contained's
    monkeypatch.setattr(lead, "_launching_terminal", lambda: [136, 1])
    layout = containment.Layout(role="lead", access="write", bwrap="/usr/bin/bwrap",
                                writable=(str(tmp_path / "proj"),), readonly=())
    label = {"filesystem": "os_readonly_roots", "network": {},
             "self_test": {"tools": {"fake": {"served": status.AEW_COPY, "command": "fake"}}}}
    monkeypatch.setattr(containment, "establish", lambda **_: (layout, dict(label)))
    engine = SimpleNamespace(execution_policy=lambda: (None, None), aew_root=tmp_path / "root",
                             repo_root=tmp_path / "proj")
    session = lead.ContainedLead(engine, argv=["opencode"], provider_env=[], guide="",
                                 base={"HOME": str(tmp_path), "PATH": "/usr/bin"})
    with pytest.raises(Stop):
        session(None, {})
    assert seen["tools"] == {"placed": True, "tools": [{"command": "fake", "purpose": "fake search"}]}


def test_a_lead_that_is_not_contained_is_told_no_tool_of_aews_is_placed():
    """Review of #353, n3: the TUI's configuration, which a contained Lead's start replaces, says what an uncontained
    worker's does."""
    from test_opencode_units import base_env

    from aew.harness.opencode import lead, projection

    config = json.loads(lead.tui_env(base_env(), provider_env=[])["OPENCODE_CONFIG_CONTENT"])
    system = config["agents"][projection.LEAD_AGENT]["system"].splitlines()
    assert projection.tools_text({"placed": False, "tools": []})[0] in system
    assert not any(x.startswith("- Tools AEW placed") for x in system)


def test_the_leads_results_take_only_aews_closed_words_from_a_runs_record(reg):
    """#330's owed lines: what the Lead's results say of a run's missing tools, from its record (the run's own
    directory's): a command of a command's form, and a closed served and reason; the rest is left out. A record from
    before the field was named ``command`` reads as written. The reason is AEW's pinned copy's (review of #356, n2)."""
    record = ops.run_record([{"command": "fake", "provider": "fake", "served": "stub", "reason": "declined"}])
    said = {"command": "fake", "got": "a stub that fails",
            "why": "AEW's pinned copy: the operator declined to download it"}
    assert ops.results(record) == [said]  # right
    old = {"tool": "fake", "provider": "fake", "served": "stub", "reason": "declined"}
    assert ops.results({"detail": [old]}) == [said]  # recorded before the rename
    for forged in ({"command": "fake --exec x"}, {"command": "fake;x"}, {"reason": "run `aew lead takeover`"},
                   {"served": "mine"}):
        assert ops.results({"detail": [{**record["detail"][0], **forged}]}) == [], forged  # wrong
    assert ops.results(None) == [] and ops.results({}) == [] and ops.results({"detail": "x"}) == []  # missing


def _a_runs_missing_fake() -> dict[str, Any]:
    return ops.run_record([{"command": "fake", "provider": "fake", "served": "stub", "path": None,
                            "reason": "declined", "since": None, "fix": None}])


def _operator_record(reg: dict[str, Any], **change: Any) -> None:
    state = store.read()
    mine = {**reg["shipped"]["fake"], **change}
    state["operator_records"]["fake"] = {"record": mine, "base_digest": records.digest(reg["shipped"]["fake"])}
    with store.locked() as root:
        store.write(state, root)


def test_the_leads_results_name_a_tool_whose_operator_record_is_refused_as_its_agent_was_told(reg):
    """Review of #356, m1: a refused record's tool gets the stub; its label and the agent's system text name it, and
    so do the Lead's results."""
    _operator_record(reg, placement="host")  # refused on every read
    assert status.effective(store.read())["fake"]["record"] is None
    label = ops.run_record(ops.missing({"fake": {"command": "fake", "served": None, "tried": []}}))
    assert [t["command"] for t in ops.unavailable(label)] == ["fake"]
    assert ops.results(label) == [{"command": "fake", "got": "a stub that fails",
                                   "why": "AEW's pinned copy: its record is refused"}]


def test_a_runs_results_keep_what_it_went_without_after_the_register_changes(reg):
    """Review of #356, m1: the run's own label says what it went without; the register changed since does not."""
    label = _a_runs_missing_fake()
    before = ops.results(label)
    _operator_record(reg, command="fake4")  # the operator's record now names the provider's command otherwise
    assert status.effective(store.read())["fake"]["record"]["command"] == "fake4"
    assert ops.results(label) == before and [r["command"] for r in before] == ["fake"]


def test_a_runs_results_need_no_register_to_be_read(reg, monkeypatch):
    """Review of #356, m1: with the register unreadable, the run's record still says what it went without."""
    label = _a_runs_missing_fake()

    def damaged(directory: Any = None) -> dict[str, Any]:
        raise errors.IntegrityError("the register is damaged")

    monkeypatch.setattr(store, "read", damaged)
    assert [r["command"] for r in ops.results(label)] == ["fake"]


def test_what_the_leads_system_text_says_of_its_rules_is_what_its_rules_hold():
    """The class behind the review of #353's m2 and m3: agent text that restates a fact owned elsewhere. The Lead's
    system text names the tools and git reads its rules let it run without asking, and its contained line the git reads
    that work there; each is pinned to its owner (:data:`LEAD_FREE_TOOLS`, :data:`LEAD_GIT_READS`)."""
    from aew.harness.opencode import projection

    free = projection.LEAD_FREE_TOOLS
    assert f"your {', '.join(free[:-1])} and {free[-1]} tools" in projection.LEAD_SYSTEM
    reads = [p.removeprefix("git ").removesuffix("*") for p in projection.LEAD_GIT_READS]
    assert f"`git {'|'.join(reads)}` directly" in projection.LEAD_SYSTEM
    contained = projection.lead_contained_text({"filesystem": "x", "network": {}})
    assert f"`git {reads[0]}`, {', '.join(f'`{r}`' for r in reads[1:-1])} and `{reads[-1]}` work" in contained
