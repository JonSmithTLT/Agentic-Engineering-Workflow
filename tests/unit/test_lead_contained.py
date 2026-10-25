"""The contained Lead's host side, on every platform (STG-05 CS-4): the operator's stored login read read-only, the
providers each login and ``--provider-env`` variable feeds, the start lines, the configuration's MCP servers, the
projection's relayed providers and contained line, the broker's three outcomes for a contained session, and the CLI's
refusal of a write to the read-only store. The sandbox itself is Linux's
(tests/integration/test_lead_contained_session.py). Synthetic logins only."""

from __future__ import annotations

import errno
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


def key_rows() -> list[tuple[str, str, int, dict[str, Any], int]]:
    return [(p, "api", 1, {"type": "key", "key": k}, 1) for p, k in KEYS.items()]


# ------------------------------------------------------------------------------------------- the stored login

def test_the_stored_login_is_read_read_only_one_row_per_provider_the_active_one_first(tmp_path):
    """Each provider's login, its active row where it has several (else its newest); an OAuth row's access token and
    expiry; a row that is not a login is passed over. The database is unchanged, and no value is in a login's repr."""
    db = store(tmp_path, [
        ("openai", "api", 0, {"type": "key", "key": "sk-old"}, 5),
        ("openai", "api", 1, {"type": "key", "key": KEYS["openai"]}, 1),
        ("anthropic", "api", None, {"type": "key", "key": "sk-older"}, 1),  # type: ignore[list-item]
        ("anthropic", "api", None, {"type": "key", "key": KEYS["anthropic"]}, 2),  # type: ignore[list-item]
        ("xai", "oauth", 1, {"type": "oauth", "methodID": "browser", "refresh": "r", "access": "acc", "expires": 9,
                             "metadata": {"accountID": "acct"}}, 1),
        ("broken", "api", 1, {"type": "key"}, 1)])
    before = db.read_bytes()
    logins, why = login.stored({"HOME": str(tmp_path)})
    assert why is None and db.read_bytes() == before
    assert [(e.integration, e.kind, e.secret) for e in logins] == [
        ("anthropic", "key", KEYS["anthropic"]), ("openai", "key", KEYS["openai"]), ("xai", "oauth", "acc")]
    assert logins[2].expires == 9 and logins[2].method == "browser" and logins[2].metadata == {"accountID": "acct"}
    assert all(e.secret not in repr(e) for e in logins)


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


def contained(tmp_path: Path, provider_env: list[str] = (), **env: str) -> lead.ContainedLead:  # type: ignore[assignment]
    return lead.ContainedLead(object(), argv=["opencode", "--standalone"], provider_env=list(provider_env),
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
    assert "opencode (key): not relayed; OpenCode's catalog gives each opencode/* model an address of its own" in text
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


def test_no_login_database_is_said_so_in_the_start_line(tmp_path, at_a_terminal):
    out = io.StringIO()
    contained(tmp_path).announce(out)
    assert "Your OpenCode logins: none (no OpenCode login database at" in out.getvalue()


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
    env = session._inside({}, SimpleNamespace(env={}), tmp_path / "run", tmp_path / "state", {}, None)
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
    session._inside({}, SimpleNamespace(env={}), tmp_path / "run1", state, {}, None)
    seeded = state / "xdg-state" / "opencode" / "model.json"
    assert json.loads(seeded.read_text()) == models
    assert sorted(p.name for p in seeded.parent.iterdir()) == ["model.json"]
    own = {"recent": [{"providerID": "anthropic", "modelID": "synthetic"}]}
    seeded.write_text(json.dumps(own))  # the Lead's own choice since
    session._inside({}, SimpleNamespace(env={}), tmp_path / "run2", state, {}, None)
    assert json.loads(seeded.read_text()) == own
    (theirs / "model.json").write_text(json.dumps({"recent": ["x" * lead.MODEL_SEED_MAX]}))
    session._inside({}, SimpleNamespace(env={}), tmp_path / "run3", tmp_path / "other", {}, None)
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
                        lambda argv, *, env, cwd, relay=False: runs.append({"argv": argv, "env": env, "relay": relay})
                        or (0, "clean"))
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


# ----------------------------------------------------------------------------- the network's tables, derived

def test_every_relayable_provider_has_an_upstream_and_a_key_variable():
    assert set(netns.PROVIDER_KEY_ENV) <= set(netns.UPSTREAMS)
    assert netns.CATALOG_ADDRESSED <= set(netns.PROVIDER_KEY_ENV)
