"""The contained Lead's host side, on every platform (STG-05 CS-4): the operator's stored login read read-only, the
providers each login and ``--provider-env`` variable feeds, the start lines, the configuration's MCP servers, the
projection's relayed providers and contained line, the broker's three outcomes for a contained session, and the CLI's
refusal of a write to the read-only store. The sandbox itself is Linux's
(tests/integration/test_lead_contained_session.py). Synthetic logins only."""

from __future__ import annotations

import errno
import fnmatch
import io
import json
import os
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew import errors
from aew.harness import lead_broker, procs
from aew.harness.containment import netns
from aew.harness.opencode import lead, login, projection

KEYS = {"openai": "sk-synthetic-openai-0001", "anthropic": "sk-ant-synthetic-0002", "opencode": "synthetic-oc-0003",
        "mystery": "synthetic-mystery-0004"}


def store(home: Path, rows: list[tuple[str, str, int, dict[str, Any], int]], path: Path | None = None) -> Path:
    """A synthetic OpenCode 2.0.18 database in ``home`` (or at ``path``), its ``credential`` table as 2.0.18 creates
    it."""
    path = path or home / ".local" / "share" / "opencode" / login.DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE credential (id text PRIMARY KEY, integration_id text, label text NOT NULL, value text "
                "NOT NULL, connector_id text, method_id text, active integer, time_created integer NOT NULL, "
                "time_updated integer NOT NULL)")
    for i, (integration, method, active, value, updated) in enumerate(rows):
        con.execute("INSERT INTO credential VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)",
                    (f"cred_{i}", integration, "label", json.dumps(value), method, active, updated, updated))
    con.commit()
    con.close()
    return path


def rewrite(db: Path, value: dict[str, Any]) -> None:
    """Every row's value, as the operator's own OpenCode would write it."""
    con = sqlite3.connect(db)
    con.execute("UPDATE credential SET value = ?", (json.dumps(value),))
    con.commit()
    con.close()


def key_rows() -> list[tuple[str, str, int, dict[str, Any], int]]:
    return [(p, "api", 1, {"type": "key", "key": k}, 1) for p, k in KEYS.items()]


# ------------------------------------------------------------------------------------------- the stored login

def test_the_stored_login_is_read_read_only_one_row_per_provider_the_active_one_first(tmp_path):
    """Each provider's login, its active row where it has several (else its newest); an OAuth row's access token and
    expiry. The database is unchanged, and no value is in a login's repr."""
    db = store(tmp_path, [
        ("openai", "api", 0, {"type": "key", "key": "sk-old"}, 5),
        ("openai", "api", 1, {"type": "key", "key": KEYS["openai"]}, 1),
        ("anthropic", "api", None, {"type": "key", "key": "sk-older"}, 1),  # type: ignore[list-item]
        ("anthropic", "api", None, {"type": "key", "key": KEYS["anthropic"]}, 2),  # type: ignore[list-item]
        ("xai", "oauth", 1, {"type": "oauth", "methodID": "browser", "refresh": "r", "access": "acc", "expires": 9,
                             "metadata": {"accountID": "acct"}}, 1)])
    before = db.read_bytes()
    logins, why = login.stored({"HOME": str(tmp_path)})
    assert why is None and db.read_bytes() == before
    assert [(e.integration, e.kind, e.secret) for e in logins] == [
        ("anthropic", "key", KEYS["anthropic"]), ("openai", "key", KEYS["openai"]), ("xai", "oauth", "acc")]
    assert logins[2].expires == 9 and logins[2].method == "browser" and logins[2].metadata == {"accountID": "acct"}
    assert all(e.secret not in repr(e) for e in logins)


@pytest.mark.parametrize("value", [
    {"type": "key"},                                                                # no key
    {"type": "oauth", "access": "synthetic-access-new"},                            # no expiry
    {"type": "oauth", "access": "synthetic-access-new", "expires": True},           # not a time
    {"type": "oauth", "access": "synthetic-access-new", "expires": 9, "metadata": ["synthetic"]},
    {"type": "oauth2", "token": "synthetic-access-new", "expires": 9},              # a type AEW does not know
    "synthetic-not-an-object"])
def test_a_providers_row_in_a_shape_aew_does_not_know_is_its_login_unread_and_never_passed_over(tmp_path, value):
    """Addendum 2, ruling 1: the operator's own OpenCode wrote the store, maybe newer than AEW's pin. A provider's
    deciding row (its active one) in a shape other than OpenCode 2.0.18's two is that provider's login, of kind
    unknown, with nothing of it read out; an older row of that provider in a known shape is never used instead."""
    store(tmp_path, [("openai", "chatgpt-browser", 1, value, 1),  # type: ignore[list-item]
                     ("openai", "chatgpt-browser", 0, chatgpt("synthetic-access-older", time.time() + 3600), 9)])
    logins, why = login.stored({"HOME": str(tmp_path)})
    assert why is None
    assert [(e.integration, e.kind, e.secret, e.expires, dict(e.metadata)) for e in logins] == [
        ("openai", login.UNKNOWN, "", None, {})]


def test_the_login_database_is_where_opencode_keeps_it(tmp_path):
    base = {"HOME": str(tmp_path / "h")}
    assert login.db_path(base) == tmp_path / "h" / ".local/share/opencode/opencode.db"
    assert login.db_path({**base, "XDG_DATA_HOME": str(tmp_path / "d")}) == tmp_path / "d/opencode/opencode.db"
    assert login.db_path({**base, "OPENCODE_DB": str(tmp_path / "x.db")}) == tmp_path / "x.db"


@pytest.mark.parametrize("make", ["missing", "not-a-database"])
def test_a_login_database_that_cannot_be_read_says_why_without_a_value(tmp_path, make):
    if make == "not-a-database":
        path = tmp_path / ".local/share/opencode/opencode.db"
        path.parent.mkdir(parents=True)
        path.write_text("SYNTHETIC not sqlite\n")
    logins, why = login.stored({"HOME": str(tmp_path)})
    assert logins == [] and why is not None and "opencode.db" in why and "SYNTHETIC" not in why


# ------------------------------------------------------------------------------- what the contained Lead relays

@pytest.fixture
def at_a_terminal(monkeypatch):
    monkeypatch.setattr(os, "isatty", lambda fd: fd == 0)
    monkeypatch.setattr(lead, "_launching_terminal", lambda: [136, 1])


def contained(tmp_path: Path, provider_env: list[str] = (), policy: dict[str, Any] | None = None,  # type: ignore[assignment]
              **env: str) -> lead.ContainedLead:
    engine = SimpleNamespace(execution_policy=lambda: (policy, None))
    return lead.ContainedLead(engine, argv=["opencode", "--standalone"], provider_env=list(provider_env),
                              guide="", base={"HOME": str(tmp_path), "PATH": "/usr/bin", **env})


def test_each_api_key_login_of_a_known_provider_is_relayed_and_the_others_say_why(tmp_path, at_a_terminal):
    """Outcome 3: every provider of the stored login whose key OpenCode reads from a variable AEW knows gets a relay;
    opencode's is never relayed (each of its models has its own catalog address, measured), an unknown provider's
    says AEW does not know its variable; the ChatGPT login is relayed as stored, with how long it has left and what
    refreshes it, and a refreshing login AEW has not measured says so. Names only."""
    in_two_hours = int((time.time() + 2 * 3600 + 60) * 1000)
    store(tmp_path, [*(r for r in key_rows() if r[0] != "openai"),
                     ("openai", "chatgpt-browser", 1, {"type": "oauth", "access": "acc", "expires": in_two_hours}, 1),
                     ("xai", "browser", 1, {"type": "oauth", "access": "xacc", "expires": in_two_hours}, 1)])
    session = contained(tmp_path)
    assert session.keys == {"anthropic": KEYS["anthropic"]} and sorted(session.refreshing) == ["openai"]
    out = io.StringIO()
    session.announce(out)
    text = out.getvalue()
    assert "anthropic (key): relayed" in text
    assert "opencode (key): not served yet: OpenCode's catalog gives each opencode/* model an address of its own, so " \
           "no relay can carry its key, and the key stays out of the Lead; the Lead's configuration switches " \
           "opencode off" in text
    assert "free" not in text and "egress proxy" not in text  # the free models are no route (2026-11-06)
    assert "mystery (key): not relayed; AEW does not know which variable" in text
    assert "openai (oauth): relayed as stored, 2 h left; AEW never refreshes it: when it expires, `opencode auth " \
           "list` at your own terminal refreshes it, and the Lead's next request works" in text
    assert "xai (oauth): not relayed; of the refreshing logins, AEW serves those whose requests it has measured: " \
           "openai" in text
    assert not any(v in text for v in [*KEYS.values(), "acc", "xacc"])


def chatgpt(access: str, expires_s: float, account: str = "synthetic-account-0007") -> dict[str, Any]:
    return {"type": "oauth", "methodID": "chatgpt-browser", "refresh": "synthetic-refresh-0005", "access": access,
            "expires": int(expires_s * 1000), "metadata": {"accountID": account}}


def test_a_refreshing_login_is_read_on_each_request_and_never_refreshed_or_written(tmp_path):
    """Addendum 1, option (a): the relay's resolver reads the operator's login store on each request, read-only, so a
    refresh by the operator's own OpenCode is used from the next request on; the account header comes from the
    stored login. Expired (or within the margin), gone, or no longer a refreshing login: the message names the
    provider and what to do (`opencode auth list` at their own terminal, then the next request works with no
    restart), and holds no value. Reading never changes the store."""
    from aew.harness.containment import relay

    db = store(tmp_path, [("openai", "chatgpt-browser", 1, chatgpt("synthetic-access-1", time.time() + 3600), 1)])
    resolve = lead.StoredLogin("openai", {"HOME": str(tmp_path)})
    before = db.read_bytes()
    assert resolve() == ("synthetic-access-1", {"chatgpt-account-id": "synthetic-account-0007"})
    assert db.read_bytes() == before
    con = sqlite3.connect(db)  # the operator's own OpenCode refreshes it
    con.execute("UPDATE credential SET value = ?", (json.dumps(chatgpt("synthetic-access-2", time.time() + 3600)),))
    con.commit()
    con.close()
    assert resolve()[0] == "synthetic-access-2"
    for value, words in ((chatgpt("synthetic-access-3", time.time() + lead.EXPIRY_MARGIN_S - 5), "has expired"),
                         ({"type": "key", "key": "sk-synthetic-now-a-key"}, "is now an API key")):
        con = sqlite3.connect(db)
        con.execute("UPDATE credential SET value = ?", (json.dumps(value),))
        con.commit()
        con.close()
        with pytest.raises(relay.Unavailable) as refused:
            resolve()
        message = str(refused.value)
        assert f"your stored openai login {words}" in message and "synthetic" not in message
    db.unlink()
    with pytest.raises(relay.Unavailable, match="your stored openai login could not be read .*the Lead's next "
                                                "request then works, with no restart"):
        resolve()


def test_an_expired_login_says_what_refreshes_it_and_that_the_next_request_works(tmp_path):
    from aew.harness.containment import relay

    store(tmp_path, [("openai", "chatgpt-browser", 1, chatgpt("synthetic-access-1", time.time() - 1), 1)])
    with pytest.raises(relay.Unavailable) as refused:
        lead.StoredLogin("openai", {"HOME": str(tmp_path)})()
    assert str(refused.value) == (
        "AEW: your stored openai login has expired, and the contained Lead never refreshes it (that would write your "
        "OpenCode's own login). Run `opencode auth list` at your own terminal: your OpenCode refreshes it there, and "
        "the Lead's next request then works, with no restart.")


def test_a_login_in_a_shape_aew_does_not_know_is_refused_and_named_at_launch_and_on_a_request(tmp_path,
                                                                                               at_a_terminal):
    """Addendum 2, ruling 1: refused with a message that names the provider, says the shape is unknown and what serves
    the provider instead, at the launch (not relayed) and on a request (the operator's OpenCode rewrote the row since).
    Never guessed, and no value in either message."""
    from aew.harness.containment import relay

    unknown = ("in a shape AEW does not know (AEW reads OpenCode 2.0.18's, and never guesses at another), so the "
               "contained Lead does not use it; to serve openai with an API key instead, start `aew opencode "
               "--provider-env OPENAI_API_KEY`")
    db = store(tmp_path, [("openai", "chatgpt-browser", 1, {"type": "oauth2", "token": "synthetic-new-shape"}, 1)])
    session = contained(tmp_path)
    assert session.refreshing == {} and session.keys == {}
    out = io.StringIO()
    session.announce(out)
    assert f"openai: not relayed; its stored login is {unknown}" in out.getvalue()
    assert "synthetic" not in out.getvalue()
    resolve = lead.StoredLogin("openai", {"HOME": str(tmp_path)})
    rewrite(db, chatgpt("synthetic-access-1", time.time() + 3600))
    assert resolve()[0] == "synthetic-access-1"
    rewrite(db, {"type": "oauth", "access": "synthetic-access-2", "expires": "tomorrow"})
    with pytest.raises(relay.Unavailable) as refused:
        resolve()
    assert str(refused.value) == f"AEW: your stored openai login is now {unknown}."


def test_a_relayed_login_close_to_expiry_is_named_at_launch_with_the_refresh_step_and_blocks_nothing(tmp_path,
                                                                                                      at_a_terminal):
    """Addendum 2, ruling 1: at the launch, a login the relay serves as stored that expires within 24 hours (the
    default; the operator's containment.lead.login_warning_h changes it) gets one line that names the provider, the
    time left and the step the operator can take now, a fresh login (addendum 3, ruling 2: a refresh happens only in
    a login's last 5 minutes); an expired one says so, with the expiry message's step. It only warns: the login is
    relayed all the same. No token in it."""
    def warned(expires_s: float, policy: dict[str, Any] | None = None) -> list[str]:
        db = store(tmp_path, [("openai", "chatgpt-browser", 1, chatgpt("synthetic-access", expires_s), 1)])
        session = contained(tmp_path, policy=policy)
        assert sorted(session.refreshing) == ["openai"]
        out = io.StringIO()
        session.announce(out)
        db.unlink()
        assert "synthetic" not in out.getvalue()
        return [ln for ln in out.getvalue().splitlines() if ln.startswith("aew opencode: your stored openai login")]

    renew = ("To renew it now, log in again at your own terminal (`opencode auth login openai`): your OpenCode stores "
             "a fresh login, and the Lead's next request uses it, with no restart.")
    assert warned(time.time() + 5 * 3600 + 60) == [
        "aew opencode: your stored openai login expires in 5 h (named when 24 h or less is left: "
        f"containment.lead.login_warning_h). {renew}"]
    assert warned(time.time() + 48 * 3600 + 60) == []
    assert warned(time.time() + 48 * 3600 + 60, {"containment": {"lead": {"login_warning_h": 72}}}) == [
        "aew opencode: your stored openai login expires in 48 h (named when 72 h or less is left: "
        f"containment.lead.login_warning_h). {renew}"]
    assert warned(time.time() - 60) == [
        "aew opencode: your stored openai login has expired. Run `opencode auth list` at your own terminal: your "
        "OpenCode refreshes it there, and the Lead's next request then works, with no restart."]


def test_a_fresh_login_is_what_the_relay_reads_next(tmp_path):
    """Addendum 3, ruling 2: the warning's step works because OpenCode 2.0.18 stores a fresh login as a new row,
    active over the provider's others (`Credential.create`, in the pinned bundle), and the relay reads the active
    row on its next request."""
    db = store(tmp_path, [("openai", "chatgpt-browser", 1, chatgpt("synthetic-access-old", time.time() + 3600), 1)])
    resolve = lead.StoredLogin("openai", {"HOME": str(tmp_path)})
    assert resolve()[0] == "synthetic-access-old"
    con = sqlite3.connect(db)  # what Credential.create does, in one transaction
    con.execute("UPDATE credential SET active = 0 WHERE integration_id = 'openai'")
    con.execute("INSERT INTO credential VALUES ('cred_new', 'openai', 'OpenAI 2', ?, NULL, 'chatgpt-browser', 1, 2, 2)",
                (json.dumps(chatgpt("synthetic-access-fresh", time.time() + 240 * 3600)),))
    con.commit()
    con.close()
    assert resolve()[0] == "synthetic-access-fresh"


def test_a_launch_without_a_stored_opencode_key_says_nothing_of_it(tmp_path, at_a_terminal):
    """Addendum 3, ruling 1: the stored opencode key's start line appears only when the operator's store holds one
    (its presence: test_each_api_key_login_of_a_known_provider_is_relayed_and_the_others_say_why)."""
    store(tmp_path, [r for r in key_rows() if r[0] == "anthropic"])
    out = io.StringIO()
    contained(tmp_path).announce(out)
    assert "anthropic (key): relayed" in out.getvalue()
    assert "opencode (" not in out.getvalue() and "not served" not in out.getvalue()


def test_the_start_stages_are_timed_in_order_for_the_label(monkeypatch, caplog):
    """Addendum 3: each start stage's seconds, in the order they ran, for the session's label, and at debug level."""
    clock = iter([10.0, 10.5, 12.0, 27.25])
    monkeypatch.setattr(lead.time, "monotonic", lambda: next(clock))
    stages = lead.StartStages()
    with caplog.at_level("DEBUG", logger=lead.__name__):
        for name in ("version", "logins", "sandbox"):
            stages.mark(name)
    assert stages.seconds == {"version": 0.5, "logins": 1.5, "sandbox": 15.25}
    assert list(stages.seconds) == ["version", "logins", "sandbox"]
    assert "aew opencode: start stage sandbox took 15.250 s" in caplog.text


def test_the_login_warning_hours_come_from_the_execution_policy_else_24():
    from aew import schemas

    assert lead.login_warning_h(None) == lead.LOGIN_WARNING_H == 24
    assert lead.login_warning_h({"containment": {"lead": {"login_warning_h": 0}}}) == 0
    for bad in (-1, True, "12", 1.5):
        policy = {"containment": {"lead": {"login_warning_h": bad}}}
        assert lead.login_warning_h(policy) == 24
        assert [e for e in schemas.iter_errors("execution", policy) if list(e.absolute_path)[:1] == ["containment"]]
    assert not [e for e in schemas.iter_errors("execution", {"containment": {"lead": {"login_warning_h": 8}}})
                if list(e.absolute_path)[:1] == ["containment"]]


def test_the_leads_own_login_row_holds_the_relays_sentinel_and_never_the_operators_login(tmp_path, at_a_terminal):
    """The Lead's own login store (in its state, never the operator's) gets one AEW row per relayed refreshing login:
    the relay's sentinel as its access token, a refresh token and account id that are placeholders, an expiry a year
    off (so the TUI never tries to refresh it), active over any other row of that provider. An AEW row of an earlier
    session whose login is gone is removed; nothing of the operator's login is written there."""
    store(tmp_path, [("openai", "chatgpt-browser", 1, chatgpt("synthetic-operator-access", time.time() + 3600), 1)])
    session = contained(tmp_path)
    state = tmp_path / "state"
    own = store(tmp_path, [("openai", "api", 1, {"type": "key", "key": "sk-lead-own"}, 1),
                           ("anthropic", "api", 1, {"type": "key", "key": "aew-relay-old"}, 1)],
                path=state / "xdg-data" / "opencode" / login.DB)
    con = sqlite3.connect(own)
    con.execute("UPDATE credential SET id = 'cred_aew_anthropic' WHERE integration_id = 'anthropic'")
    con.commit()
    con.close()
    token = "aew-relay-" + "0" * 32
    session._seed_logins(None, {}, "", state, {"openai": token})
    con = sqlite3.connect(own)
    rows = {r[0]: r[1:] for r in con.execute("SELECT id, integration_id, active, value FROM credential")}
    con.close()
    assert sorted(rows) == ["cred_0", "cred_aew_openai"]
    integration, active, value = rows["cred_aew_openai"]
    seeded = json.loads(value)
    assert (integration, active, seeded["access"], seeded["methodID"]) == ("openai", 1, token, "chatgpt-browser")
    assert seeded["refresh"] == "aew-relay-no-refresh" and seeded["metadata"] == {"accountID": "aew-relay-placeholder"}
    assert seeded["expires"] / 1000 > time.time() + 300 * 86400
    assert rows["cred_0"][1] == 0  # the Lead's own earlier openai row is no longer the active one
    blob = b"".join(p.read_bytes() for p in own.parent.iterdir() if p.is_file())
    assert b"synthetic-operator-access" not in blob and b"synthetic-account-0007" not in blob


def _lead_store(state: Path, table: str, rows: list[tuple[Any, ...]] = ()) -> Path:  # type: ignore[assignment]
    """The Lead's own store in ``state`` with a ``credential`` table made by ``table``, holding ``rows``."""
    own = state / "xdg-data" / "opencode" / login.DB
    own.parent.mkdir(parents=True)
    con = sqlite3.connect(own)
    con.execute(table)
    for row in rows:
        con.execute(f"INSERT INTO credential VALUES ({', '.join('?' * len(row))})", row)  # noqa: S608 -- placeholders
    con.commit()
    con.close()
    return own


@pytest.mark.parametrize("table, differs", [
    ("CREATE TABLE credential (id text PRIMARY KEY, integration_id text, label text NOT NULL, secret text NOT NULL, "
     "active integer, time_created integer NOT NULL, time_updated integer NOT NULL)", "no value"),
    ("CREATE TABLE credential (id text PRIMARY KEY, integration_id text, label text NOT NULL, value text NOT NULL, "
     "connector_id text, method_id text, active integer, time_created integer NOT NULL, time_updated integer NOT NULL, "
     "scope text)", "an extra scope"),
    ("CREATE TABLE credential (id text PRIMARY KEY, integration_id text, label text NOT NULL, value blob NOT NULL, "
     "connector_id text, method_id text, active integer, time_created integer NOT NULL, time_updated integer NOT NULL)",
     "value blob, not text"),
], ids=["a-column-missing", "an-extra-column", "a-changed-type"])
def test_a_credential_table_not_exactly_opencodes_skips_the_seed_and_writes_nothing(tmp_path, at_a_terminal, table,
                                                                                    differs):
    """E118: the seed writes only to a ``credential`` table exactly like 2.0.18's. Any other (a column missing or
    extra, or one whose declared type changed, as a newer OpenCode's might be) skips the seed: an ``sqlite3.Error``,
    which the start reports as the login it could not give the Lead this session, and no row is written. With an
    extra nullable column the write itself would succeed, so the outcome is what is checked."""
    store(tmp_path, [("openai", "chatgpt-browser", 1, chatgpt("synthetic-operator-access", time.time() + 3600), 1)])
    session = contained(tmp_path)
    state = tmp_path / "state"
    width = len(sqlite3.connect(":memory:").execute(table).execute("SELECT * FROM credential").description)
    own = _lead_store(state, table, [("cred_lead_own", "openai", "own", *["x"] * (width - 3))])
    before = own.read_bytes()
    with pytest.raises(login.StoreSchemaChanged, match=differs) as raised:
        session._seed_logins(None, {}, "", state, {"openai": "aew-relay-" + "0" * 32})
    assert isinstance(raised.value, sqlite3.Error)  # the start's own skip path (`lead.py`, "cannot use it")
    assert own.read_bytes() == before
    con = sqlite3.connect(own)
    assert [r[0] for r in con.execute("SELECT id FROM credential")] == ["cred_lead_own"]  # no AEW row
    con.close()


def test_the_credential_schema_aew_checks_is_the_one_its_tests_seed_and_it_writes_a_subset_of():
    """The schema the seed checks is the one the session tests' synthetic stores use, and every column it writes is
    in it (so the check and the write cannot drift apart)."""
    import lead_session

    con = sqlite3.connect(":memory:")
    con.execute(lead_session.CREDENTIAL_TABLE)
    login.require_schema(con, "credential", login.CREDENTIAL_SCHEMA)
    assert set(login.CREDENTIAL_COLUMNS) <= dict(login.CREDENTIAL_SCHEMA).keys()


# The two schemas OpenCode 2.0.18's migrations give the ``permission`` table, read in the pinned bundle (E118).
PERMISSION_SCHEMAS = {
    "first": "CREATE TABLE permission (project_id text PRIMARY KEY, time_created integer, time_updated integer, "
             "data text NOT NULL)",
    "later": "CREATE TABLE permission (id text PRIMARY KEY, project_id text NOT NULL, action text NOT NULL, "
             "resource text NOT NULL, time_created integer, time_updated integer)"}
# A session table with its own permission rules, as 2.0.18 keeps them (``session_v2``; the columns that matter here)
SESSION_TABLE = "CREATE TABLE {name} (id text PRIMARY KEY, title text, permission text, time_updated integer)"
ALLOW_ALL = json.dumps([{"action": "*", "resource": "*", "effect": "allow"}])


def saved_permissions(db: Path, schema: str, session_table: str | None = "session_v2") -> None:
    """A synthetic Lead store holding saved permissions in ``schema`` and two sessions, one with its own rules,
    beside a credential row that must stay."""
    store(db.parent, [("openai", "api", 1, {"type": "key", "key": "sk-lead-own"}, 1)], path=db)
    con = sqlite3.connect(db)
    con.execute(PERMISSION_SCHEMAS[schema])
    width = len(con.execute("SELECT * FROM permission").description)
    con.executemany(f"INSERT INTO permission VALUES ({', '.join('?' * width)})",  # noqa: S608 -- placeholders only
                    [(f"p{i}", *[f"v{i}"] * (width - 1)) for i in range(3)])
    if session_table:
        con.execute(SESSION_TABLE.format(name=session_table))
        con.executemany(f"INSERT INTO {session_table} VALUES (?, ?, ?, 1)",  # noqa: S608 -- the test's own name
                        [("ses_ruled", "ruled", ALLOW_ALL), ("ses_plain", "plain", None)])
    con.commit()
    con.close()


def _count(db: Path, sql: str) -> int:
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


@pytest.mark.parametrize("session_table", ["session_v2", "session"])
@pytest.mark.parametrize("schema", sorted(PERMISSION_SCHEMAS))
def test_the_saved_permissions_and_session_rules_are_cleared_in_either_schema_and_nothing_else_is(tmp_path, schema,
                                                                                                  session_table):
    """E118: every saved permission goes, and every session's own permission rules (which 2.0.18 evaluates after the
    agent's, so an `allow` there would answer an `ask`) are set to null; the sessions and the credential stay."""
    db = tmp_path / login.DB
    saved_permissions(db, schema, session_table)
    assert login.clear_saved_permissions(db, tmp_path) == 4  # three saved, one session's rules
    assert _count(db, "SELECT COUNT(*) FROM permission") == 0
    assert _count(db, f"SELECT COUNT(*) FROM {session_table} WHERE permission IS NOT NULL") == 0  # noqa: S608
    assert _count(db, f"SELECT COUNT(*) FROM {session_table}") == 2  # noqa: S608 -- the test's own name
    assert _count(db, "SELECT COUNT(*) FROM credential") == 1
    assert login.clear_saved_permissions(db, tmp_path) == 0


def test_a_session_table_without_its_rules_column_refuses_the_clear(tmp_path):
    """A session table that keeps its rules somewhere AEW does not know is not cleared by guessing: the clear raises,
    and the start is refused (below)."""
    db = tmp_path / login.DB
    saved_permissions(db, "later", session_table=None)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE session_v2 (id text PRIMARY KEY, rules text)")
    con.commit()
    con.close()
    with pytest.raises(login.StoreSchemaChanged, match="session_v2 table has no permission column"):
        login.clear_saved_permissions(db, tmp_path)
    assert _count(db, "SELECT COUNT(*) FROM permission") == 3  # rolled back: nothing half-cleared


def test_a_store_with_no_saved_permissions_is_left_as_it_is(tmp_path):
    assert login.clear_saved_permissions(tmp_path / login.DB, tmp_path) == 0  # no database: nothing saved
    assert not (tmp_path / login.DB).exists()  # and none is made
    db = store(tmp_path, [], path=tmp_path / login.DB)
    before = db.read_bytes()
    assert login.clear_saved_permissions(db, tmp_path) == 0  # no permission or session table: nothing kept
    assert db.read_bytes() == before


# ------------------------------------------------------------------------------- the store is the Lead's own
needs_symlinks = pytest.mark.skipif(os.name == "nt", reason="the contained Lead is Linux's, and making a symlink "
                                                            "needs a privilege on Windows")


def _operators_store(tmp_path: Path) -> tuple[Path, bytes]:
    """The operator's own store, with a saved permission, a session's rules and a login, and its bytes."""
    operator = tmp_path / "operator" / login.DB
    operator.parent.mkdir(parents=True)
    saved_permissions(operator, "later")
    return operator, operator.read_bytes()


@needs_symlinks
@pytest.mark.parametrize("link", ["store", "directory", "sidecar", "parent"])
def test_neither_writer_follows_a_link_out_of_the_leads_state(tmp_path, at_a_terminal, link):
    """E118: AEW writes the Lead's store on the host, so the store, its directory and each SQLite sidecar must be a
    regular file (a directory) whose real path is inside the Lead's state directory. One that leads elsewhere refuses
    the start, from the clear and from the login seed alike, naming the path and its own reason, and the store it
    leads to is untouched. ``parent``: every path is of the right type, but a directory above them leads elsewhere,
    so only their real path shows it."""
    operator, before = _operators_store(tmp_path)
    state = tmp_path / "state"
    data = state / "xdg-data" / "opencode"
    if link == "parent":  # xdg-data leads to a real tree whose opencode/opencode.db is the operator's store
        operator = tmp_path / "operator-data" / "opencode" / login.DB
        operator.parent.mkdir(parents=True)
        saved_permissions(operator, "later")
        before = operator.read_bytes()
        state.mkdir()
        (state / "xdg-data").symlink_to(tmp_path / "operator-data", target_is_directory=True)
        named = data
    elif link == "directory":
        data.parent.mkdir(parents=True)
        data.symlink_to(operator.parent, target_is_directory=True)
        named = data
    else:
        data.mkdir(parents=True)
        if link == "store":
            (data / login.DB).symlink_to(operator)
            named = data / login.DB
        else:
            saved_permissions(data / login.DB, "later")
            named = data / (login.DB + "-wal")
            named.symlink_to(tmp_path / "operator" / (login.DB + "-wal"))
    with pytest.raises(errors.ContainmentUnavailable, match="regular file inside its state directory") as clear:
        login.clear_saved_permissions(data / login.DB, state)
    with pytest.raises(errors.ContainmentUnavailable) as seed:
        contained(tmp_path)._seed_logins(None, {}, "", state, {"openai": "aew-relay-" + "0" * 32})
    for refused in (clear.value, seed.value):
        assert refused.details == {"reason": login.STORE_OUTSIDE_STATE, "path": str(named)}
        assert str(named) in refused.message and "move it aside" in refused.message
    assert operator.read_bytes() == before


def test_a_regular_store_inside_the_state_passes_and_one_that_is_not_a_file_is_refused(tmp_path):
    state = tmp_path / "state"
    data = state / "xdg-data" / "opencode"
    data.mkdir(parents=True)
    login.own_store(data / login.DB, state)  # nothing there yet: nothing to refuse
    (data / login.DB).mkdir()  # a directory where the store goes
    with pytest.raises(errors.ContainmentUnavailable) as refused:
        login.own_store(data / login.DB, state)
    assert refused.value.details["reason"] == login.STORE_OUTSIDE_STATE


def _start_until_the_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[lead.ContainedLead, Path]:
    """A contained start driven on any platform up to the Lead's projection, which stops it: the sandbox is a stand-in
    on the session's own network, and the run directory is retired as on any failed start."""
    from aew.harness import containment

    layout = SimpleNamespace(private_network=False, tree_masks=(), net_dir=None)
    monkeypatch.setattr(containment, "establish", lambda **kw: (layout, {"filesystem": "test", "network": {}}))
    monkeypatch.setattr(containment, "tree_masks_line", lambda layout: None)

    def stop(*a: Any, **kw: Any) -> None:
        raise RuntimeError("synthetic: the start stops at the projection")

    monkeypatch.setattr(projection, "lead_config", stop)
    session = contained(tmp_path)
    session.engine = SimpleNamespace(aew_root=tmp_path / ".aew", repo_root=tmp_path,
                                     execution_policy=lambda: ({}, None))
    return session, tmp_path / ".aew" / lead.LEAD_DIR / "xdg-data" / "opencode" / login.DB


def test_every_contained_start_clears_the_leads_saved_permissions_before_its_session(tmp_path, monkeypatch,
                                                                                    at_a_terminal):
    """E118: each contained session starts with no saved permission and no session rules, whether or not it seeds a
    login (none here)."""
    session, db = _start_until_the_projection(tmp_path, monkeypatch)
    db.parent.mkdir(parents=True)
    saved_permissions(db, "later")
    with pytest.raises(RuntimeError, match="stops at the projection"):
        session(None, {})
    assert _count(db, "SELECT COUNT(*) FROM permission") == 0
    assert _count(db, "SELECT COUNT(*) FROM session_v2 WHERE permission IS NOT NULL") == 0


def test_a_contained_start_whose_store_cannot_be_cleared_is_refused_with_the_step_that_fits(tmp_path, monkeypatch,
                                                                                            at_a_terminal):
    """E118: a clear that fails refuses the start, naming the store and the step that fits: a store that is not a
    database is moved aside (starting again would fail the same way); a busy one is waited for."""
    session, db = _start_until_the_projection(tmp_path, monkeypatch)
    db.parent.mkdir(parents=True)
    db.write_bytes(b"this is not a database" * 100)
    with pytest.raises(errors.ContainmentUnavailable, match="no saved permissions") as refused:
        session(None, {})
    assert refused.value.details == {"reason": "saved_permissions", "path": str(db)}
    assert f"move {db} aside" in refused.value.message and "once nothing holds" not in refused.value.message
    busy = login.clear_failure_step(db, sqlite3.OperationalError("database is locked"))
    assert busy == f"start `aew opencode` again once nothing holds {db}"


def test_provider_env_feeds_its_providers_relay_and_never_the_lead_shell(tmp_path, at_a_terminal):
    """Outcome 3: `--provider-env NAME` feeds the relay of the provider that reads NAME, over the stored login; a
    proxy variable is the relays' own route; any other variable, or opencode's, is refused before anything starts."""
    store(tmp_path, key_rows())
    session = contained(tmp_path, ["OPENAI_API_KEY", "HTTPS_PROXY"], OPENAI_API_KEY="sk-synthetic-fed",
                        HTTPS_PROXY="http://proxy.example:3128")
    assert session.keys["openai"] == "sk-synthetic-fed" and session.fed == {"OPENAI_API_KEY": "openai"}
    out = io.StringIO()
    session.announce(out)
    assert "--provider-env OPENAI_API_KEY feeds the openai relay on the host; the Lead's shell sees only a " \
           "placeholder" in out.getvalue() and "openai (key): fed by --provider-env instead" in out.getvalue()
    for name in ("VENDOR_KEY", "OPENCODE_API_KEY"):
        with pytest.raises(errors.UsageError, match=f"--provider-env {name}: the contained Lead passes"):
            contained(tmp_path, [name], **{name: "synthetic"})


def test_the_contained_lead_needs_a_terminal_and_a_passable_provider_variable(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "isatty", lambda fd: False)
    with pytest.raises(errors.UsageError, match="runs on a terminal AEW relays"):
        contained(tmp_path)
    monkeypatch.setattr(os, "isatty", lambda fd: True)
    monkeypatch.setattr(lead, "_launching_terminal", lambda: [136, 1])
    with pytest.raises(errors.UsageError, match="--provider-env OPENAI_API_KEY"):
        contained(tmp_path, ["OPENAI_API_KEY"])  # unset


def test_a_contained_lead_with_no_provider_relayed_is_refused_naming_the_rule_and_the_operators_steps(
        tmp_path, at_a_terminal):
    """The designer's ruling of 2026-11-06: with no key and no refreshing login relayed, the Lead's configuration
    leaves it no model (OpenCode's own providers are switched off), so `aew opencode` is refused at start with
    `provider_key_missing`, quoting the published rule and naming the operator's own steps: log in with their own
    OpenCode outside AEW, or feed a key, then start again. The start lines still say what was found, and no longer
    say the free models work. Right case: a fed key, or a refreshing login, passes; wrong case: no login database, or
    an empty one, is refused; missing case: an opencode key alone (never relayed) is refused too."""
    def refused(session: lead.ContainedLead) -> errors.HarnessIncompatible:
        out = io.StringIO()
        session.announce(out)
        assert "free models work" not in out.getvalue()
        with pytest.raises(errors.HarnessIncompatible) as caught:
            session.require_provider()
        return caught.value

    exc = refused(contained(tmp_path))
    assert exc.details["reason"] == netns.PROVIDER_KEY_MISSING == "provider_key_missing"
    assert netns.FREE_TIER_RULE in exc.message and "https://opencode.ai/docs/zen/" in exc.message
    assert "`opencode auth login`" in exc.message and "`--provider-env NAME`" in exc.message
    assert "ANTHROPIC_API_KEY, GOOGLE_GENERATIVE_AI_API_KEY, OPENAI_API_KEY" in exc.message
    assert "OPENCODE_API_KEY" not in exc.message  # never relayed to the Lead, so never offered as a fix
    store(tmp_path / "empty", [])
    refused(contained(tmp_path / "empty"))
    store(tmp_path / "oc", [("opencode", "api", 1, {"type": "key", "key": KEYS["opencode"]}, 1)])
    refused(contained(tmp_path / "oc", OPENCODE_API_KEY="synthetic-oc-env"))
    contained(tmp_path, ["OPENAI_API_KEY"], OPENAI_API_KEY="sk-synthetic-fed").require_provider()  # fed: passes
    in_two_hours = int((time.time() + 2 * 3600 + 60) * 1000)
    store(tmp_path / "chatgpt",
          [("openai", "chatgpt-browser", 1, {"type": "oauth", "access": "acc", "expires": in_two_hours}, 1)])
    contained(tmp_path / "chatgpt").require_provider()  # a refreshing login relayed as stored: passes


def test_the_lead_is_refused_before_a_seat_or_sandbox_when_no_provider_is_relayed(tmp_path, monkeypatch,
                                                                                at_a_terminal):
    """`aew opencode` refuses in `run`, after the start lines and before `run_session`, which takes the seat and
    builds the sandbox (the designer's ruling: refused at start, before the sandbox)."""
    started: list[Any] = []
    monkeypatch.setattr(lead, "check_version", lambda: "2.0.18")
    monkeypatch.setattr(lead, "command", lambda engine, extra: ["opencode", "--standalone"])
    monkeypatch.setattr(lead, "guide_of", lambda engine: "")
    monkeypatch.setattr(lead, "contained_here", lambda: True)
    monkeypatch.setattr(lead_broker, "require_credential", lambda acquire: None)
    monkeypatch.setattr(lead_broker, "run_session", lambda *a, **k: started.append(a) or {})
    monkeypatch.setattr(os, "environ", {"HOME": str(tmp_path), "PATH": "/usr/bin"})
    engine = SimpleNamespace(execution_policy=lambda: (None, None), repo_root=tmp_path)
    with pytest.raises(errors.HarnessIncompatible, match="no provider is relayed to the contained Lead"):
        lead.run(engine, acquire=False, session_label=None, keep_seat=False, provider_env=[], extra_args=[],
                 print_config=False)
    assert started == []


# ---------------------------------------------------------------- where the start reaches the tools AEW brings

def _start_order(tmp_path: Path, monkeypatch: Any, *, contained_: bool, environ: dict[str, str],
                 provider_env: list[str], credential: bool = True,
                 execution: dict[str, Any] | None = None) -> list[Any]:
    """Drive `lead.run` to its session with the steps that matter recorded in order: the start line, the credential
    check, the tools hook (``consent.at_lead_start``, with its ``asking``), the session that takes the seat and builds
    the sandbox, and a refusal. Synthetic environment only: no terminal read, no network, no download."""
    from aew import doctor
    from aew.capability import consent

    calls: list[Any] = []
    readiness = doctor.readiness_lines
    monkeypatch.setattr(doctor, "readiness_lines",
                        lambda engine, who: (lambda text: calls.append(("readiness", text)) or text)(
                            readiness(engine, who)))
    monkeypatch.setattr(lead, "check_version", lambda: "2.0.18")
    monkeypatch.setattr(lead, "command", lambda engine, extra: ["opencode", "--standalone"])
    monkeypatch.setattr(lead, "guide_of", lambda engine: "")
    monkeypatch.setattr(lead, "contained_here", lambda: contained_)
    announce = lead.ContainedLead.announce
    monkeypatch.setattr(lead.ContainedLead, "announce",
                        lambda self, out: calls.append("announce") or announce(self, out))
    monkeypatch.setattr(lead_broker.WeakerLead, "precheck", lambda self: calls.append("precheck"))

    def require_credential(acquire: bool) -> None:
        calls.append("credential")
        if not credential:
            raise errors.AEWError("synthetic: no Lead credential")

    monkeypatch.setattr(lead_broker, "require_credential", require_credential)
    monkeypatch.setattr(lead_broker, "run_session", lambda *a, **k: calls.append("session") or {})
    monkeypatch.setattr(consent, "at_lead_start", lambda *a, **k: calls.append(("tools", k.get("asking", True))))
    monkeypatch.setattr(os, "environ", {"HOME": str(tmp_path), "PATH": "/usr/bin", **environ})
    engine = SimpleNamespace(execution_policy=lambda: (execution, None), repo_root=tmp_path,
                             aew_root=tmp_path / ".aew")
    try:
        lead.run(engine, acquire=False, session_label=None, keep_seat=False, provider_env=provider_env, extra_args=[],
                 print_config=False)
    except errors.AEWError as exc:
        calls.append(("refused", exc.message.split(",")[0]))
    return calls


def test_a_contained_start_the_provider_refusal_ends_never_reaches_the_tools_hook(tmp_path, monkeypatch,
                                                                                  at_a_terminal):
    """Review of #343's merge, m1: #340's refusal comes after the start line and before the tools AEW brings, so a
    start that cannot run is never asked about downloads."""
    calls = _start_order(tmp_path, monkeypatch, contained_=True, environ={}, provider_env=[])
    assert calls == ["credential", ("readiness", ""), "announce",
                     ("refused", "no provider is relayed to the contained Lead")], calls


def test_a_contained_start_that_proceeds_asks_about_the_tools_after_its_checks_and_before_its_session(
        tmp_path, monkeypatch, at_a_terminal):
    """Review of #343's merge, m1: a contained start with a provider reaches the tools hook, asking, after its start
    line and refusals, and before the session takes the seat and builds the sandbox."""
    calls = _start_order(tmp_path, monkeypatch, contained_=True, environ={"OPENAI_API_KEY": KEYS["openai"]},
                         provider_env=["OPENAI_API_KEY"])
    assert calls == ["credential", ("readiness", ""), "announce", ("tools", True), "session"], calls


@pytest.mark.parametrize("contained_", [True, False], ids=["contained", "uncontained"])
def test_aew_opencode_prints_each_failing_readiness_row_with_its_fix_first_and_starts_as_before(
        tmp_path, monkeypatch, at_a_terminal, capsys, contained_):
    """E125: what a launch from this terminal would meet (a provider variable the policy names, unset here) is
    printed when the operator starts the Lead, with its fix, right after the credential check (a missing credential
    still refuses before any start line, #340); it refuses nothing the start did not refuse before (the Lead's own
    launches would be refused, naming the same). Names only, never a value."""
    environ = {"OPENAI_API_KEY": KEYS["openai"]}
    calls = _start_order(tmp_path, monkeypatch, contained_=contained_, environ=environ,
                         provider_env=["OPENAI_API_KEY"], execution={"provider_env": ["VUAT_UNSET_KEY"]})
    readiness = calls[calls.index("credential") + 1]
    assert readiness[0] == "readiness" and readiness[1].startswith(
        "aew opencode: readiness FAIL (provider-env): a harness launch from this Lead session will be refused: "
        "VUAT_UNSET_KEY is not set in this environment: set VUAT_UNSET_KEY in the terminal you start AEW from"), calls
    # the fix for this site: the session about to start keeps its environment (review of #360, m2)
    assert readiness[1].rstrip().endswith("so set VUAT_UNSET_KEY first: exit the session, set it in the terminal you "
                                          "start AEW from, then start `aew opencode` again"), readiness[1]
    assert "doctor checks" not in readiness[1]
    assert calls[-1] == "session", calls  # the start went on to its session
    assert readiness[1] in capsys.readouterr().err
    assert KEYS["openai"] not in readiness[1]


@pytest.mark.parametrize("credential, expected", [
    (True, ["precheck", "credential", ("readiness", ""), ("tools", False), "session"]),
    (False, ["precheck", "credential", ("refused", "synthetic: no Lead credential")]),
])
def test_an_uncontained_start_says_its_tools_line_only_after_the_credential_check(tmp_path, monkeypatch,
                                                                                  credential, expected):
    """Review of #343's merge, m2: off Linux a missing credential refuses first, before any start line (#340), so the
    tools line (``asking=False``: said and logged, never asked) comes after it, and never on a start it refuses."""
    calls = _start_order(tmp_path, monkeypatch, contained_=False, environ={}, provider_env=[], credential=credential)
    assert calls == expected, calls


def test_provider_variables_in_the_environment_are_named_with_whether_the_lead_serves_them(tmp_path, at_a_terminal):
    """The Lead's check: a provider key in the operator's environment, rather than stored, is never silent. One whose
    provider has a relay is named as not given to the Lead, with `--provider-env` as the way to feed it; opencode's is
    named as not served (addendum 2, ruling 2). A fed one is not named again. Names only."""
    env = {"ANTHROPIC_API_KEY": "sk-ant-synthetic-env", "OPENAI_API_KEY": "sk-synthetic-env",
           "OPENCODE_API_KEY": "synthetic-oc-env"}
    out = io.StringIO()
    contained(tmp_path, **env).announce(out)
    text = out.getvalue()
    assert "aew opencode: ANTHROPIC_API_KEY, OPENAI_API_KEY are set in your environment and not given to the Lead; " \
           "`aew opencode --provider-env NAME` feeds one to its provider's relay on the host." in text
    assert "aew opencode: OPENCODE_API_KEY is set in your environment: not served yet: OpenCode's catalog gives each " \
           "opencode/* model an address of its own" in text
    assert not any(v in text for v in env.values())
    out = io.StringIO()
    contained(tmp_path, ["ANTHROPIC_API_KEY"], **env).announce(out)
    assert "aew opencode: OPENAI_API_KEY is set in your environment and not given to the Lead" in out.getvalue()


# ------------------------------------------------------------------------------------ the operator's MCP servers

def test_the_operators_mcp_servers_are_named_from_their_configuration_with_comments_and_trailing_commas(tmp_path):
    """The designer's condition: the session-start notice names the MCP servers the contained Lead leaves out, from
    the operator's OpenCode configuration as OpenCode reads it (JSONC; V2's `mcp.servers` and the older flat `mcp`)."""
    conf = tmp_path / ".config" / "opencode"
    conf.mkdir(parents=True)
    (conf / "opencode.jsonc").write_text('{\n  // a comment with "quotes" and https://x\n  "mcp": {"servers": {\n'
                                         '    "docs": {"url": "https://docs.example/mcp"}, /* block */\n'
                                         '    "jira": {"command": ["jira-mcp"]},\n  }},\n}\n', encoding="utf-8")
    other = tmp_path / "elsewhere.json"
    other.write_text('{"mcp": {"local": {"type": "local"}}}', encoding="utf-8")
    (conf / "config.json").write_text("{not json", encoding="utf-8")
    names, unread = lead.operator_mcp_servers({"HOME": str(tmp_path), "OPENCODE_CONFIG": str(other)})
    assert names == ["docs", "jira", "local"] and unread == [str(conf / "config.json")]
    assert lead._jsonc('{"a": "//not a comment", "b": [1, 2,],}') == {"a": "//not a comment", "b": [1, 2]}


def test_the_start_lines_name_the_mcp_servers_left_out(tmp_path, at_a_terminal):
    conf = tmp_path / ".config" / "opencode"
    conf.mkdir(parents=True)
    (conf / "opencode.json").write_text('{"mcp": {"servers": {"docs": {}}}}', encoding="utf-8")
    out = io.StringIO()
    contained(tmp_path).announce(out)
    assert "your OpenCode configuration is not loaded in the contained Lead; its MCP servers are left out: docs" \
        in out.getvalue()


def test_the_operators_tui_preferences_reach_the_lead_without_their_plugins_and_last_a_session(tmp_path, at_a_terminal):
    """Addendum 1, item 2: the operator's `cli.json` is read on the host and its plugins dropped (A-38's CAPR-05); the
    rest goes in as OPENCODE_CLI_CONFIG_CONTENT, which OpenCode merges over the session's own file, so a preference
    changed inside lasts that session. The start line says so and names the plugins left out; an unreadable file
    says it could not be read, and the Lead uses OpenCode's defaults."""
    conf = tmp_path / ".config" / "opencode"
    conf.mkdir(parents=True)
    prefs = {"theme": {"name": "synthetic"}, "keybinds": {"leader": "ctrl+x"}}
    (conf / "cli.json").write_text(json.dumps({**prefs, "plugins": ["synthetic-plugin", {"name": "other-plugin"}]}))
    session = contained(tmp_path)
    assert session.preferences == prefs
    out = io.StringIO()
    session.announce(out)
    assert "your TUI preferences come from your own OpenCode at each start; one you change in the Lead lasts this " \
           "session only; its TUI plugins are left out: synthetic-plugin, other-plugin." in out.getvalue()
    env = session._inside({}, SimpleNamespace(env={}, tree_masks=()), tmp_path / "run", tmp_path / "state", {}, None)
    assert json.loads(env["OPENCODE_CLI_CONFIG_CONTENT"]) == prefs
    assert env["XDG_CONFIG_HOME"].startswith(str(tmp_path / "run"))  # the TUI's own writes: this session's file
    (conf / "cli.json").write_text("{not json")
    out = io.StringIO()
    contained(tmp_path).announce(out)
    assert "could not read your TUI preferences" in out.getvalue() and "the Lead uses OpenCode's defaults" in \
        out.getvalue()


def test_the_leads_recent_models_are_seeded_once_from_the_operators_and_never_the_prompt_history(tmp_path,
                                                                                                   at_a_terminal):
    """Addendum 1, item 3: when the Lead's state is created, the operator's `model.json` (recent and favourite models:
    no credential, no prompt) is copied in, once; a later session keeps the Lead's own. The prompt history is never
    copied (it carries other projects' prompts), nor a `model.json` too large to be a list of models."""
    theirs = tmp_path / ".local" / "state" / "opencode"
    theirs.mkdir(parents=True)
    models = {"recent": [{"providerID": "openai", "modelID": "gpt-5.5"}]}
    (theirs / "model.json").write_text(json.dumps(models))
    (theirs / "prompt-history.jsonl").write_text('{"input": "synthetic prompt of another project"}\n')
    session = contained(tmp_path)
    state = tmp_path / "state"
    session._inside({}, SimpleNamespace(env={}, tree_masks=()), tmp_path / "run1", state, {}, None)
    seeded = state / "xdg-state" / "opencode" / "model.json"
    assert json.loads(seeded.read_text()) == models
    assert sorted(p.name for p in seeded.parent.iterdir()) == ["model.json"]
    own = {"recent": [{"providerID": "anthropic", "modelID": "synthetic"}]}
    seeded.write_text(json.dumps(own))  # the Lead's own choice since
    session._inside({}, SimpleNamespace(env={}, tree_masks=()), tmp_path / "run2", state, {}, None)
    assert json.loads(seeded.read_text()) == own
    (theirs / "model.json").write_text(json.dumps({"recent": ["x" * lead.MODEL_SEED_MAX]}))
    session._inside({}, SimpleNamespace(env={}, tree_masks=()), tmp_path / "run3", tmp_path / "other", {}, None)
    assert not (tmp_path / "other" / "xdg-state" / "opencode" / "model.json").exists()


# ------------------------------------------------------------------------------------------------ the projection

LABEL = {"filesystem": "os_readonly_roots",
         "network": {"mode": "proxy_only", "provider_relays": {"anthropic": "https://api.anthropic.com/v1",
                                                               "openai": "https://api.openai.com/v1"},
                     "egress_policy": "any_public"}}


def test_the_contained_lead_config_points_each_relayed_provider_at_its_relay_and_carries_one_contained_line():
    """Outcome 3 and 7: provider-level baseURLs only (no model is made up in the list), OpenAI's over plain HTTP; the
    system text gains one line from the label, after AEW's rules and before the guide."""
    config = projection.lead_config("GUIDE", contained=LABEL, relays={"openai": "http://127.0.0.1:4112/v1",
                                                                      "anthropic": "http://127.0.0.1:4111/v1"})
    assert config["providers"] == {"anthropic": {"settings": {"baseURL": "http://127.0.0.1:4111/v1"}},
                                   "openai": {"settings": {"baseURL": "http://127.0.0.1:4112/v1", "transport": "http"}}}
    system = config["agents"][projection.LEAD_AGENT]["system"]
    line = projection.lead_contained_text(LABEL)
    assert system == f"{projection.LEAD_SYSTEM}\n{line}\n\nGUIDE"
    assert "providers `anthropic`, `openai` through AEW's relays" in line and "over https through `HTTPS_PROXY`" in line
    for refused in ("desktop", "clipboard bus", "browser tools", "private or host addresses", "commit fails"):
        assert refused in line
    assert projection.lead_config("GUIDE") == {k: v for k, v in config.items() if k != "providers"} | {
        "agents": {projection.LEAD_AGENT: {**config["agents"][projection.LEAD_AGENT],
                                           "system": f"{projection.LEAD_SYSTEM}\n\nGUIDE"}}}


def test_a_contained_line_without_relays_or_egress_says_it_reaches_nothing():
    line = projection.lead_contained_text({"filesystem": "os_readonly_roots", "network": {"mode": "isolated"}})
    assert "The session reaches nothing outside it." in line


# ------------------------------------------- addendum 11: a command that asks is requested, and nothing is loosened

def effect(rules: list[dict[str, str]], action: str, resource: str = "*") -> str:
    """OpenCode's evaluation for these patterns: the last rule whose action and resource match wins, with `*` as the
    only wildcard. fnmatch's `[...]` classes and OpenCode's optional trailing ` *` (a bare `aew` matches `aew *`) are
    not modelled (#304 review, n2)."""
    out = "ask"
    for r in rules:
        if fnmatch.fnmatchcase(action, r["action"]) and fnmatch.fnmatchcase(resource, r["resource"]):
            out = r["effect"]
    return out


def test_the_lead_rules_are_unchanged_a_command_still_asks_and_an_edit_or_a_subagent_is_denied():
    """Addendum 11 changes the Lead's text, never its rules. The shell runs `aew` and read-only git; any other
    command, the tests and a commit among them, asks the operator; an edit and a subagent are denied. Nothing else is
    allowed or denied, and a contained session's rules are the same. Since 2026-11-06 the Lead denies reading `.env`
    files as invocations do, and its git reads with an option that writes a file or runs a program ask (the
    designer)."""
    rules = projection.lead_config()["agents"][projection.LEAD_AGENT]["permissions"]
    assert projection.lead_config(contained=LABEL)["agents"][projection.LEAD_AGENT]["permissions"] == rules
    assert {(r["action"], r["resource"]) for r in rules if r["effect"] == "allow"} == {
        ("read", "*"), ("glob", "*"), ("grep", "*"), ("question", "*"), (f"{projection.LEAD_MCP_SERVER}_*", "*"),
        ("shell", "aew *"), ("shell", "git status*"), ("shell", "git diff*"), ("shell", "git log*"),
        ("shell", "git show*"), ("read", "*.env.example")}
    assert {(r["action"], r["resource"]) for r in rules if r["effect"] == "deny"} == {
        ("edit", "*"), ("subagent", "*"), ("read", "*.env"), ("read", "*.env.*")}
    # The asks are AEW's own, never OpenCode's default for an unmatched action (#304 review, n1).
    assert {(r["action"], r["resource"]) for r in rules if r["effect"] == "ask"} == {
        ("*", "*"), ("shell", "*"), *(("shell", pattern) for pattern in projection.LEAD_GIT_ASKS)}
    for command in ("aew status", "git status --short", "git diff HEAD", "git log -1", "git show HEAD"):
        assert effect(rules, "shell", command) == "allow", command
    for command in ("python -m pytest -q", "bash scripts/check.sh", "git commit -m wip", "git push", "rm -rf build"):
        assert effect(rules, "shell", command) == "ask", command
    assert effect(rules, "edit", "src/aew/cli/main.py") == "deny" and effect(rules, "subagent", "general") == "deny"
    assert effect(rules, "webfetch", "https://example.com") == "ask"


def test_the_lead_denies_reading_env_files_with_the_invocations_own_three_rules_in_their_order(tmp_path):
    """The Lead's permissions deny reading `.env` files, as invocations' already do: one list, used by both, and it
    comes after the `read` allow so it wins (the designer, 2026-11-06). The project is synthetic."""
    (tmp_path / ".env").write_text("SYNTHETIC=not-a-secret\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("SYNTHETIC=not-a-secret\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("SYNTHETIC=\n", encoding="utf-8")
    lead_rules = projection.lead_config()["agents"][projection.LEAD_AGENT]["permissions"]
    worker = projection.permissions(SimpleNamespace(extra={}, role="reviewer"), [])
    shared = list(projection.ENV_READ_RULES)
    assert [(r["effect"], r["resource"]) for r in shared] == [("deny", "*.env"), ("deny", "*.env.*"),
                                                               ("allow", "*.env.example")]
    for rules in (lead_rules, worker):
        start = rules.index(shared[0])
        assert rules[start:start + 3] == shared
        assert rules.index(projection.rule("read", "allow")) < start
    for name, want in ((".env", "deny"), (".env.local", "deny"), (".env.example", "allow"), ("README.md", "allow")):
        assert effect(lead_rules, "read", (tmp_path / name).as_posix()) == want, name


def test_the_leads_git_reads_that_write_a_file_or_run_a_program_ask_and_the_plain_reads_stay_allowed():
    """The Lead's auto-allowed git reads no longer cover options that write files or run a configured program:
    `--output` and `--ext-diff` ask wherever they follow the subcommand, as one argument or two (the designer,
    2026-11-06). A global option before the subcommand matches no allow, so it asks too. Nothing here runs git."""
    rules = projection.lead_config()["agents"][projection.LEAD_AGENT]["permissions"]
    for command in ("git diff", "git diff HEAD", "git log -5", "git log --oneline -3", "git show HEAD",
                    "git status --short"):
        assert effect(rules, "shell", command) == "allow", command
    for command in ("git diff --output=x", "git log --output=x", "git show HEAD --output=x", "git diff --output x",
                    "git log -p --output x", "git diff --ext-diff", "git log -p --ext-diff", "git show --ext-diff HEAD",
                    "git -C /tmp diff", "git -C /tmp log"):
        assert effect(rules, "shell", command) == "ask", command


def test_the_leads_git_reads_ask_for_a_comparison_outside_the_working_tree_and_for_a_read_naming_an_env_file():
    """The designer, 2026-11-06: the Lead's auto-allowed git reads also ask for comparisons outside the working tree
    and for reads naming `.env` files. Other spellings and shell globs aren't matched; a containment-level mask is the
    follow-on. The text says so, and `.env.example` stays readable. Nothing here runs git."""
    rules = projection.lead_config()["agents"][projection.LEAD_AGENT]["permissions"]
    for command in ("git diff --no-index a b", "git diff --no-index -- a b", "git diff /dev/null b",
                    "git diff --stat /dev/null b", "git diff .env", "git diff HEAD -- .env.local", "git log -p -- .env",
                    "git show HEAD:.env", "git show HEAD:config/.env.production"):
        assert effect(rules, "shell", command) == "ask", command
    for command in ("git diff", "git log -5", "git show HEAD", "git diff HEAD -- src/aew", "git log --oneline -3"):
        assert effect(rules, "shell", command) == "allow", command
    assert "(`.env` files aren't readable; `.env.example` is)" in projection.LEAD_SYSTEM
    assert "a `.env` file named among them" in " ".join(projection.LEAD_SYSTEM.split())


def test_the_lead_text_requests_a_command_that_asks_and_keeps_edits_and_commits_with_invocations():
    """Addendum 11: two sentences, read together, made the Lead refuse a command its rules ask about ("a permission
    approval wouldn't override them", the operator's trial of 2026-10-30). The text now says to request such a command
    and run it once the operator approves, that an approval is not working around a refusal, and that a refusal is a
    deny rule's or the containment's, never retried another way. Edits and commits stay with invocations.

    The request is the command itself: OpenCode's prompt is the one approval, and a yes typed in chat is not a second
    gate. The Lead may say in a line what it is about to run, but does not wait for a reply (#304 review, m2)."""
    system = projection.LEAD_SYSTEM
    assert "anything else needs the operator" not in system
    assert ("Any other command asks the operator's permission first: when the operator asks for one, such as running "
            "the tests or a script, or one is needed to do what they asked, request it by running it: OpenCode asks "
            "the operator, and it runs once they approve. That prompt is the approval: you may say in a line what you "
            "are about to run, but do not wait for a reply in chat first. If they decline, do not try it another "
            "way.") in system
    assert "You cannot edit files in this session" in system
    assert "Editing files and committing stay with invocations, whatever the command: dispatch one for them." in system
    line = projection.lead_contained_text(LABEL)
    assert "Do not work around a refusal:" not in line
    assert line.endswith("A refusal is what a deny rule or this containment returns. Do not work around one: tell the "
                         "operator what you needed and why, so they can do it at their own terminal or widen AEW's "
                         "containment settings where a setting exists. Running a command the operator approved is not "
                         "working around anything.")


# ----------------------------------------------------------------------- the broker's outcomes for a contained run

class Broker:
    superseded = None

    def __init__(self, *_: Any) -> None:
        self.server = type("S", (), {"private_dir": "/tmp/aew-bridge-x"})()
        self.closed = False

    @property
    def env(self) -> dict[str, str]:
        return {lead_broker.ENV_ENDPOINT: "/tmp/aew-bridge-x/s", lead_broker.ENV_KEY: "00"}

    def start(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class Engine:
    repo_root = "."

    def __init__(self) -> None:
        self.released: list[str] = []
        self.store = type("St", (), {"current": lambda _s: {"revision": 3, "invocations": {}}})()

    def lead_acquire(self, **_: Any) -> dict[str, str]:
        return {"token": "synthetic-token"}

    def lead_release(self, *, token: str, expect_rev: int) -> None:
        self.released.append(token)


@pytest.fixture
def session_parts(monkeypatch):
    runs: list[dict[str, Any]] = []
    monkeypatch.setattr(lead_broker, "LeadBroker", Broker)
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    monkeypatch.setattr(procs, "run_session_tree",
                        lambda argv, *, env, cwd, relay=False, survivors=None:
                        runs.append({"argv": argv, "env": env, "relay": relay}) or (0, "clean"))
    return runs


def test_a_contained_session_runs_its_sandbox_on_the_relay_and_reports_its_label(session_parts):
    closed = []
    harness = lead_broker.Harness(argv=["bwrap", "tui"], env={"X": "1"}, relay=True,
                                  label={"filesystem": "os_readonly_roots"}, close=lambda: closed.append(1))
    seen = {}

    def build(bridge_dir, child_env):
        seen.update(bridge_dir=bridge_dir, env=child_env)
        return harness

    out = lead_broker.run_session(Engine(), ["tui"], acquire=True, session_label=None, keep_seat=True, env={},
                                  contained=build)
    assert session_parts == [{"argv": ["bwrap", "tui"], "env": {"X": "1"}, "relay": True}]
    assert seen["bridge_dir"] == "/tmp/aew-bridge-x" and lead_broker.ENV_ENDPOINT in seen["env"]
    assert out["containment"] == {"filesystem": "os_readonly_roots"} and closed == [1]


def test_a_weaker_session_runs_as_it_is_off_the_relay_labelled_so(session_parts):
    weaker = lead_broker.Harness(argv=["tui"], env={"Y": "1"}, relay=False,
                                 label={"filesystem": "workdir_separation_only", "weaker_because": "row 4"},
                                 close=lambda: None)
    out = lead_broker.run_session(Engine(), ["tui"], acquire=True, session_label=None, keep_seat=True, env={},
                                  contained=lambda *_: weaker)
    assert session_parts == [{"argv": ["tui"], "env": {"Y": "1"}, "relay": False}]
    assert out["containment"]["weaker_because"] == "row 4"


def test_a_refused_contained_session_runs_nothing_and_frees_the_seat_it_took(session_parts, monkeypatch):
    """Outcome 1 and 6: required and not established, nothing runs, the broker closes, and a seat this session acquired
    is released again (its credential existed only in this session)."""
    engine = Engine()

    def refuse(*_):
        raise errors.ContainmentUnavailable("containment self-test failed: row 4 (terminal): ...")

    with pytest.raises(errors.ContainmentUnavailable, match="row 4"):
        lead_broker.run_session(engine, ["tui"], acquire=True, session_label=None, keep_seat=False, env={},
                                contained=refuse)
    assert session_parts == [] and engine.released == ["synthetic-token"]
    monkeypatch.setenv("AEW_LEAD_TOKEN", "synthetic-held")
    held = Engine()
    with pytest.raises(errors.ContainmentUnavailable):
        lead_broker.run_session(held, ["tui"], acquire=False, session_label=None, keep_seat=False, env={},
                                contained=refuse)
    assert held.released == []  # a seat held by the operator's own credential stays theirs


# --------------------------------------------------------------------------- outcome 7: the read-only store, said

def test_a_write_to_the_read_only_store_inside_the_contained_lead_is_refused_by_design(monkeypatch):
    from aew.cli import main

    erofs = OSError(errno.EROFS, "Read-only file system", "/p/.aew/state/control.json")
    monkeypatch.delenv(lead.CONTAINED_ENV, raising=False)
    assert main._contained_refusal(erofs) is None  # outside the sandbox: the error as it is
    monkeypatch.setenv(lead.CONTAINED_ENV, "1")
    refusal = main._contained_refusal(erofs)
    assert isinstance(refusal, errors.PermissionDenied) and refusal.details["reason"] == "lead_contained"
    assert "contained by design" in refusal.message and "/p/.aew/state/control.json is read-only" in refusal.message
    assert main._contained_refusal(OSError(errno.EACCES, "denied")) is None


def test_the_cli_answers_a_read_only_store_write_with_the_typed_refusal(monkeypatch, capsys):
    from aew.cli import main

    def handler(_args):
        raise OSError(errno.EROFS, "Read-only file system", ".aew/state/x")

    monkeypatch.setenv(lead.CONTAINED_ENV, "1")
    monkeypatch.setattr(main, "_run", lambda args, argv, h: handler(args))
    assert main._run_main(["status"]) == errors.PermissionDenied.exit_code
    assert json.loads(capsys.readouterr().err)["error"]["details"]["reason"] == "lead_contained"


def test_the_contained_lead_names_the_masks_in_its_project_at_launch_and_hands_them_to_its_sandbox(
        tmp_path, monkeypatch, capsys, at_a_terminal):
    """Quick check of #283 at 3ad586ed, m5, and CS-4 addendum 7: the contained Lead's launch prints the line naming
    each mask in its project, and its sandbox gets those masks by path, so AEW's CLI there explains a write that meets
    one. A launch with none prints nothing of them."""
    from aew import process_kind
    from aew.harness import containment

    class Stop(Exception):
        pass

    def stop(*_: Any, **__: Any) -> None:
        raise Stop

    masks = ((str(tmp_path / "proj" / "deploy.key"), "the link /h/.ssh/deploy"),)
    monkeypatch.setattr(projection, "lead_config", stop)  # the step after the line: the launch goes no further
    for tree_masks in (masks, ()):
        session = contained(tmp_path)
        session.engine.aew_root, session.engine.repo_root = tmp_path / "root", tmp_path / "proj"
        layout = containment.Layout(role="lead", access="write", bwrap="/usr/bin/bwrap",
                                    writable=(str(tmp_path / "proj"),), readonly=(), tree_masks=tree_masks)
        monkeypatch.setattr(containment, "establish",
                            lambda layout=layout, **_: (layout, {"filesystem": "os_readonly_roots", "network": {}}))
        with pytest.raises(Stop):
            session(None, {})
        err = capsys.readouterr().err
        env = session._inside({}, layout, tmp_path / "run", tmp_path / "state", {}, None)
        if tree_masks:
            assert f"aew opencode: {containment.tree_masks_line(layout)}.\n" in err, err
            assert json.loads(env[process_kind.LEAD_MASKS_ENV]) == [list(m) for m in masks]
        else:
            assert "masked in place" not in err and process_kind.LEAD_MASKS_ENV not in env


@pytest.mark.parametrize("code", [errno.EROFS, errno.EACCES])
def test_a_write_that_meets_a_mask_in_the_leads_project_is_explained_as_the_mask_by_its_path(tmp_path, monkeypatch,
                                                                                              capsys, code):
    """CS-4 addendum 7: inside the contained Lead, a write that meets a mask in its project (a file mask gives EROFS or
    EACCES, by how the file is opened) is refused as that mask, recognised by its path from the masks the layout
    handed the sandbox, and never explained as `.aew/`; with AEW's CLI the same through its typed refusal. Another
    path keeps its own answer."""
    from aew import process_kind
    from aew.cli import main

    mask = str(tmp_path / "p" / "keys")
    monkeypatch.setenv(lead.CONTAINED_ENV, "1")
    monkeypatch.setenv(process_kind.LEAD_MASKS_ENV, json.dumps([[mask, "the link /h/.ssh/keys"]]))
    refusal = main._contained_refusal(OSError(code, "denied", os.path.join(mask, "id")))
    assert isinstance(refusal, errors.PermissionDenied) and refusal.details["reason"] == "lead_masked"
    assert refusal.details["mask"] == mask and refusal.details["by"] == "the link /h/.ssh/keys"
    assert "edit it at your own terminal" in refusal.message and ".aew" not in refusal.message
    other = main._contained_refusal(OSError(code, "denied", str(tmp_path / "p" / "keys-not")))
    assert (other is None) if code == errno.EACCES else other.details["reason"] == "lead_contained"

    def handler(_args):
        with open(os.path.join(mask, "id"), "a"):
            pass

    monkeypatch.setattr(main, "_run", lambda args, argv, h: handler(args))
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError(code, "denied", a[0])))
    assert main._run_main(["status"]) == errors.PermissionDenied.exit_code
    assert json.loads(capsys.readouterr().err)["error"]["details"]["reason"] == "lead_masked"


# ----------------------------------------------------------------------------- the network's tables, derived

def test_every_relayable_provider_has_an_upstream_and_a_key_variable():
    assert set(netns.PROVIDER_KEY_ENV) <= set(netns.UPSTREAMS)
    assert netns.CATALOG_ADDRESSED <= set(netns.PROVIDER_KEY_ENV)


def _weaker_lead(tmp_path: Path, monkeypatch, layout: Any, label: dict[str, Any]) -> lead_broker.Harness:
    """The contained Lead's own call, with containment.establish giving ``layout`` and ``label``."""
    from aew.harness import containment

    monkeypatch.setattr(containment, "establish", lambda **kw: (layout, dict(label)))
    engine = SimpleNamespace(execution_policy=lambda: ({"containment": {"mode": "allow_weaker"}}, None),
                             repo_root=tmp_path / "repo", aew_root=tmp_path / "repo" / ".aew")
    (tmp_path / "repo").mkdir()
    built = lead.ContainedLead(engine, argv=["opencode"], provider_env=[], guide="",
                               base={"HOME": str(tmp_path), "PATH": "/usr/bin"})
    return built(None, {lead_broker.ENV_ENDPOINT: "/tmp/aew-bridge-x/s"})


def _live_lead(harness: lead_broker.Harness) -> list[dict[str, Any]]:
    from aew.harness import weaker_register as W

    assert harness.env[W.MARKER] == harness.entry.data["marker"] and harness.env[W.MARKER].endswith("label.json")
    return [x for x in W.read().live if x["kind"] == "lead_opencode"]


def test_a_contained_lead_the_policy_allows_to_run_weaker_is_live_in_the_register_while_it_runs(tmp_path, monkeypatch,
                                                                                                at_a_terminal):
    """#321 review, F5: with no layout (allowed weaker by the policy), the TUI runs as it is, entered in the register
    of weaker contexts before it starts and marked."""
    from aew.harness import containment

    harness = _weaker_lead(tmp_path, monkeypatch, None, containment.label(contained=False, reason="allowed weaker"))
    harness.entry.started()
    assert [x["why"] for x in _live_lead(harness)] == ["running"]


def test_a_contained_lead_on_the_hosts_network_is_live_in_the_register_while_it_runs(tmp_path, monkeypatch,
                                                                                      at_a_terminal):
    """#321 review, F5: a sandbox on the host's network (containment.network.mode: shared) is weaker, and enters the
    register like any weaker context."""
    from aew.harness import containment

    shared = {"filesystem": "os_readonly_roots", "network": {"mode": "shared"}, "self_test": {"ok": True},
              "process_ownership": "pid_namespace"}
    monkeypatch.setattr(containment, "tree_masks_line", lambda layout: "")
    monkeypatch.setattr(containment, "bwrap_argv", lambda layout, argv, cwd=None, path=None: ["bwrap", *argv])
    monkeypatch.setattr(netns, "shim_argv", lambda spec, argv: list(argv))
    monkeypatch.setattr(projection, "lead_config", lambda *a, **k: {})
    monkeypatch.setattr(lead.ContainedLead, "_inside", lambda self, *a, **k: {"PATH": "/usr/bin"})
    monkeypatch.setattr(lead.ContainedLead, "_retire", lambda self, *a, **k: None)
    harness = _weaker_lead(tmp_path, monkeypatch, SimpleNamespace(private_network=False), shared)
    assert harness.entry is not None, "a weaker label enters the register"
    harness.entry.started()
    assert harness.relay and [x["why"] for x in _live_lead(harness)] == ["running"]
    assert harness.env["AEW_CONTEXT"] == harness.entry.data["marker"], "the sandboxed TUI carries its marker"
