"""The contained Lead's session end to end, on Linux (STG-05 CS-4, outcomes 1 to 3, 6 and 7).

`aew opencode` runs at a terminal (a pseudo-terminal this test holds as the operator's), with its broker on the host,
and a fake TUI (the `opencode` launcher of tests/helpers/lead_session.py) in the Lead's sandbox, on the relayed
terminal. The fake TUI either acts as the Lead's model would, through `aew` and the broker (the fake agent), or calls
each relayed provider the way its SDK would. The operator's home is synthetic: no real OpenCode login is ever read.
tests/integration/test_opencode_lead.py has the session's Windows path, which runs labelled not contained.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import threading
import time
from typing import Any

import pytest
from fake_harness import contains_credential
from lead_session import KEYS, RECENT_MODELS, SECRET, Upstream, at_the_terminal, guide_of, make_lab, synthetic_home

from aew.harness import procs
from aew.harness.containment import netns
from aew.harness.opencode import lead, projection

pytestmark = [pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                                 reason="the Lead is contained on Linux (bubblewrap); Windows runs it labelled not "
                                 "contained"), pytest.mark.autopsy]


# --------------------------------------------------------------------------------------- outcomes 1, 2, 6 and 7

def test_the_contained_lead_acts_through_its_broker_from_its_sandbox_on_its_relayed_terminal(tmp_path):
    """The TUI runs in a self-tested `lead` sandbox (rows 1 to 6 on the label, with the network: `proxy_only`, any
    public address), on the relayed terminal, which gets its settings back at the end. Its environment is AEW's: no
    AEW credential, no provider key, no operator `XDG_*` or OpenCode configuration, AEW's XDG directories under
    `.aew/local/harness`, both proxy variables at the egress proxy, and the contained line in its system text. From
    there the Lead's model mutates AEW state through the broker, a credential-emitting command is refused, and a read
    works."""
    lab, tui = make_lab(tmp_path)
    try:
        home = synthetic_home(tmp_path)
        (tui / "mode").write_text("agent")
        sync = tmp_path / "sync"
        (tui / "tui-script.json").write_text(json.dumps([
            {"do": "dump_env", "path": str(sync / "env")},
            {"do": "aew", "args": ["lead", "show"]},
            {"do": "lead", "args": ["checkpoint", "--next", "dispatch T-0001 with --launch"]},
            {"do": "aew", "args": ["lead", "handoff", "offer", "--expect-rev", "1"]},
            {"do": "aew", "args": ["resume", "--json"]},
            {"do": "read", "path": str(home / ".local/share/opencode/opencode.db")}]))
        done = at_the_terminal(lab, home, extra={"XDG_RUNTIME_DIR": str(tmp_path / "operator-runtime"),
                                                 "XDG_CURRENT_DESKTOP": "operator-desktop",
                                                 "XDG_DATA_DIRS": str(tmp_path / "operator-data-dirs")})
        assert done["code"] == 0, done["stderr"][-3000:]
        out = done["result"]
        transcript = (tui / "tui.jsonl").read_text() if (tui / "tui.jsonl").exists() else ""
        assert out["exit"] == 0, (done["stdout"].split(procs.TERMINAL_LEAVE)[0][-3000:], transcript)
        assert (out["seat"], out["opencode"]) == ("held by your AEW_LEAD_TOKEN", "2.0.18")
        label = out["containment"]
        assert label["filesystem"] == "os_readonly_roots" and sorted(label["self_test"]["rows"]) == list("123456")
        assert all(r["ok"] for r in label["self_test"]["rows"].values())
        assert label["network"]["mode"] == "proxy_only" and label["network"]["egress_policy"] == "any_public"
        run_dir = lab.aew_root / "local" / "harness" / "runs" / label["session"]
        assert json.loads((run_dir / "label.json").read_text())["session"] == label["session"]
        # addendum 3: each start stage's seconds, so a slow start names its stage
        assert list(label["start_s"]) == ["version", "logins", "seat", "sandbox", "network"], label["start_s"]
        assert all(isinstance(s, float) and s >= 0 for s in label["start_s"].values())
        assert json.loads((run_dir / "label.json").read_text())["start_s"] == label["start_s"]
        assert done["restored"]
        assert json.loads((tui / "tui-argv.json").read_text()) == ["--standalone", str(lab.root)]

        env = json.loads((sync / "env").read_text())
        assert SECRET not in json.dumps(env) and not contains_credential(json.dumps(env))
        assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "OPENAI_API_KEY", "AEW_OPENCODE_BIN",
                    "OPENCODE_CONFIG"} & set(env)
        assert {"AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"} <= set(env) and env[lead.CONTAINED_ENV] == "1"
        harness = str(lab.aew_root / "local" / "harness")
        for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"):
            assert env[name].startswith(harness), (name, env[name])
        assert {k for k in env if k.startswith("XDG_")} == {"XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                                                            "XDG_CACHE_HOME", "XDG_RUNTIME_DIR"}  # none the operator's
        egress = f"http://127.0.0.1:{netns.EGRESS_PORT}"
        assert env["HTTPS_PROXY"] == env["HTTP_PROXY"] == egress and "127.0.0.1" in env["NO_PROXY"]
        assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == projection.lead_config(guide_of(lab), contained=label)
        assert "your OpenCode configuration is not loaded in the contained Lead; its MCP servers are left out: docs" \
            in done["stderr"]
        # addendum 1: the operator's TUI preferences without their plugins; their recent models, never their prompts
        assert json.loads(env["OPENCODE_CLI_CONFIG_CONTENT"]) == {"theme": {"name": "synthetic"}}
        assert "its TUI plugins are left out: synthetic-plugin" in done["stderr"]
        own_state = lab.aew_root / "local" / "harness" / "lead" / "xdg-state" / "opencode"
        assert json.loads((own_state / "model.json").read_text()) == RECENT_MODELS
        assert not (own_state / "prompt-history.jsonl").exists()

        steps = {e["i"]: e["result"] for e in map(json.loads, (tui / "tui.jsonl").read_text().splitlines())}
        assert steps[1]["exit"] == 0 and "revision" in steps[1]["stdout_json"], steps[1]  # a read, lock-free
        assert steps[2]["exit"] == 0, steps[2]  # a Lead mutation, carried out by the broker on the host
        assert ((steps[3].get("stderr_json") or {}).get("error") or {}).get("code") == "USAGE"
        assert steps[4]["stdout_json"]["lead_note"] == "dispatch T-0001 with --launch"
        assert steps[5] == {"readable": False, "error": "FileNotFoundError"}  # the login store is masked
    finally:
        lab.cleanup()


# --------------------------------------------------------------------------------------------------- outcome 3

def test_every_provider_in_the_stored_login_has_its_own_relay_and_the_sandbox_holds_only_sentinels(tmp_path):
    """Each provider of the operator's stored login whose key OpenCode reads from a known variable gets its own relay
    on the host: from inside, a call to the baseURL its configuration names, with the variable its SDK reads, reaches
    that provider's upstream with the real key, while the sandbox holds only a sentinel. opencode's key is not served
    (its models carry their own catalog address; addendum 2, ruling 2): the start line says so, and the key is not
    inside at all. `--provider-env` feeds google's relay."""
    ups = {p: Upstream() for p in ("openai", "anthropic", "google")}
    try:
        lab, tui = make_lab(tmp_path, upstreams={p: u.url for p, u in ups.items()})
        try:
            home = synthetic_home(tmp_path, KEYS)
            (tui / "mode").write_text("providers")
            (tui / "variables.json").write_text(json.dumps(netns.PROVIDER_KEY_ENV))
            (tui / "look.json").write_text(json.dumps([str(home / ".local/share/opencode"),
                                                       str(home / ".config/opencode")]))
            fed = "synthetic-google-fed-0005"
            done = at_the_terminal(lab, home, "--provider-env", "GOOGLE_GENERATIVE_AI_API_KEY",
                                   extra={"GOOGLE_GENERATIVE_AI_API_KEY": fed})
            assert done["code"] == 0, done["stderr"][-3000:]
            inside = json.loads((tui / "inside.json").read_text())
            blob = json.dumps(inside["env"])
            for value in (*KEYS.values(), fed, SECRET):
                assert value not in blob
            relays = done["result"]["containment"]["network"]["provider_relays"]
            assert relays == {p: u.url for p, u in ups.items()}
            for provider, upstream in ups.items():
                sentinel = inside["env"][netns.PROVIDER_KEY_ENV[provider]]
                assert sentinel.startswith("aew-relay-")
                assert inside["calls"][provider][0] == 200, inside["calls"]
                want = fed if provider == "google" else KEYS[provider]
                assert upstream.seen == [("/v1/probe", f"Bearer {want}")], (provider, upstream.seen)
            assert "OPENCODE_API_KEY" not in inside["env"] and "opencode" not in inside["calls"]
            # empty under the mask, or absent where the home is under /tmp, private inside (the mask itself:
            # tests/integration/test_lead_containment.py, whose home is not)
            assert all(seen in ([], False) for seen in inside["visible"].values()), inside["visible"]
            # addendum 2, ruling 2 (and addendum 3's two halves): the stored opencode key fails closed, said at the
            # start, and the Lead's view holds no key: not its environment, nor anything it read, nor its own store
            assert "opencode (key): not served yet: OpenCode's catalog gives each opencode/* model an address of its " \
                   "own" in done["stderr"]
            assert KEYS["opencode"] not in json.dumps(inside)
            own = lab.aew_root / "local" / "harness" / "lead" / "xdg-data" / "opencode"
            assert not any(KEYS["opencode"].encode() in p.read_bytes() for p in own.glob("*") if p.is_file())
            assert "--provider-env GOOGLE_GENERATIVE_AI_API_KEY feeds the google relay on the host" in done["stderr"]
        finally:
            lab.cleanup()
    finally:
        for u in ups.values():
            u.close()


def chatgpt(access: str, expires_s: float) -> dict[str, Any]:
    """A synthetic ChatGPT login's stored value (OpenCode 2.0.18's shape)."""
    return {"type": "oauth", "methodID": "chatgpt-browser", "refresh": "synthetic-refresh-0005", "access": access,
            "expires": int(expires_s * 1000), "metadata": {"accountID": "synthetic-account-0007"}}


def test_the_chatgpt_login_is_relayed_as_stored_and_an_expired_one_says_what_refreshes_it(tmp_path):
    """Addendum 1, option (a): the operator's ChatGPT login (synthetic, and expired) gets a relay; the TUI uses its
    own login row, whose access token is the relay's sentinel. The first request is answered 401 with what to do
    (`opencode auth list` at the operator's terminal, then the next request works). The operator's own OpenCode then
    refreshes the login (the test writes the operator's row, as it would), and the next request, in the same session,
    reaches the upstream with the new access token and the stored account id; so does the one after the next
    refresh, read again. AEW wrote nothing of the operator's, and nothing of the operator's login is inside."""
    up = Upstream()
    try:
        lab, tui = make_lab(tmp_path, upstreams={"openai": up.url})
        try:
            home = synthetic_home(tmp_path, oauth={"openai": chatgpt("synthetic-access-expired", time.time() - 10)})
            operator = home / ".local" / "share" / "opencode" / "opencode.db"
            fresh = [json.dumps(chatgpt(f"synthetic-access-fresh-{n}", time.time() + 3600)) for n in (1, 2)]
            for name, text in (("mode", "providers"), ("variables.json", "{}"), ("look.json", "[]"),
                               ("oauth.json", '["openai"]'), ("rounds.json", "3")):
                (tui / name).write_text(text)

            def refresh() -> None:  # the operator's own OpenCode, before the second and the third request
                for n, value in enumerate(fresh, start=1):
                    deadline = time.monotonic() + 90
                    while not (tui / f"round-{n}").exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    con = sqlite3.connect(operator)
                    con.execute("UPDATE credential SET value = ?", (value,))
                    con.commit()
                    con.close()
                    (tui / f"go-{n}").write_text("x")

            refresher = threading.Thread(target=refresh, daemon=True)
            refresher.start()
            done = at_the_terminal(lab, home)
            refresher.join(10)
            assert done["code"] == 0, done["stderr"][-3000:]
            assert "openai (oauth): relayed as stored, expired now" in done["stderr"]
            # addendum 2, ruling 1: the launch names it, and goes on
            assert "aew opencode: your stored openai login has expired. Run `opencode auth list` at your own " \
                   "terminal" in done["stderr"]
            assert done["result"]["containment"]["network"]["provider_relays"] == {"openai": up.url}
            assert "lead_logins" in done["result"]["containment"]["start_s"]  # its rows are a stage of their own
            inside = json.loads((tui / "inside.json").read_text())
            status, body = inside["calls"]["openai"]
            assert status == 401, inside["calls"]
            assert body.startswith("AEW: your stored openai login has expired") and "`opencode auth list`" in body
            assert "the Lead's next request then works, with no restart" in body
            assert [r["openai"][0] for r in inside["later"]] == [200, 200], inside["later"]
            assert up.seen == [("/v1/probe", f"Bearer synthetic-access-fresh-{n}") for n in (1, 2)]
            assert up.accounts == ["synthetic-account-0007"] * 2
            [row] = inside["logins"]
            assert row["integration"] == "openai" and row["access"].startswith("aew-relay-"), row
            assert row["metadata"] == {"accountID": "aew-relay-placeholder"}
            blob = json.dumps(inside)
            assert not any(s in blob for s in ("synthetic-access-", "synthetic-account-", "synthetic-refresh-"))
            con = sqlite3.connect(operator)
            assert [v for (v,) in con.execute("SELECT value FROM credential")] == fresh[1:]  # only the refreshes wrote
            con.close()
        finally:
            lab.cleanup()
    finally:
        up.close()


# --------------------------------------------------------------------------------------------- outcomes 1 and 6

def test_a_lead_whose_containment_fails_is_refused_under_required_and_runs_labelled_under_allow_weaker(tmp_path):
    """Required (the default): nothing runs, and the refusal says what failed and what fixes it. Allow-weaker: the TUI
    runs as it does elsewhere, labelled workdir_separation_only with the reason, and the start line says so."""
    missing = str(tmp_path / "no-such-root")
    lab, tui = make_lab(tmp_path, writable_extra=[missing])
    try:
        home = synthetic_home(tmp_path)
        (tui / "mode").write_text("agent")
        (tui / "tui-script.json").write_text(json.dumps([]))
        refused = at_the_terminal(lab, home)
        assert refused["code"] != 0 and refused["error"]["code"] == "CONTAINMENT_UNAVAILABLE", refused["stderr"]
        assert "not an existing directory" in refused["error"]["message"] and refused["restored"]
        assert not (tui / "tui-argv.json").exists()
    finally:
        lab.cleanup()
    weaker_root = tmp_path / "weaker"
    weaker_root.mkdir()
    lab, tui = make_lab(weaker_root, mode="allow_weaker", writable_extra=[missing])
    try:
        home = synthetic_home(weaker_root)
        (tui / "mode").write_text("agent")
        (tui / "tui-script.json").write_text(json.dumps([]))
        done = at_the_terminal(lab, home)
        assert done["code"] == 0, done["stderr"][-3000:]
        label = done["result"]["containment"]
        assert label["filesystem"] == "workdir_separation_only"
        assert "not an existing directory" in label["weaker_because"]
        assert "the Lead runs NOT contained" in done["stderr"]
        assert (tui / "tui-argv.json").exists()
    finally:
        lab.cleanup()
