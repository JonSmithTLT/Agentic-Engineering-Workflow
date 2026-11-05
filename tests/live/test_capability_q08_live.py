"""CAPR-Q08's rows against a real OpenCode, on Linux, with egress open (the designer's CAP-1 ruling 1; opt-in:
``--live``).

AEW's payload is missing or refused, on a host with its own copy and on one without. A real ``opencode-cli serve`` runs
in the sandbox AEW establishes for it, and a real file search makes it look ``rg`` up, through ``/api/fs/find`` in a
directory with no repository, where OpenCode searches with ripgrep. Each row reads:

* **nothing was downloaded:** no file under the server's own ``$XDG_CACHE_HOME/opencode/bin``, and no request for
  github.com in the log of a proxy every outbound request of this server is pointed at;
* **a host copy, if used,** is named in the status as unpinned;
* **with no copy,** the search fails, the stub's text is what fails it, and the status names the cause.

The proxy refuses everything, and logs it: its log is the proof, not the refusal (the ruling), and a request that
ignored ``HTTPS_PROXY`` would not be in it. Ablation A3 (the stub removed) shows its log does see the download's
request, so nothing is ever fetched from github.com by this file. It needs no model. Run it with::

    AEW_OPENCODE_BIN=/path/to/opencode-cli pytest --live tests/live/test_capability_q08_live.py -p no:xdist -q
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from aew.capability import bind, ops, records, status, store
from aew.capability import payload as P
from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import layout as L
from aew.harness.opencode import adapter, projection
from aew.harness.opencode.client import Server

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or shutil.which("bwrap") is None
    or (not os.environ.get(adapter.BIN_ENV) and adapter.default_binary() is None),
    reason="Linux bubblewrap containment and an OpenCode binary (set AEW_OPENCODE_BIN)")

GITHUB = "github.com"


class LoggingProxy:
    """A forward proxy that refuses everything and logs each request's first line."""

    def __init__(self) -> None:
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.log: list[str] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(5)
                    self.log.append(conn.recv(4096).split(b"\r\n")[0].decode("latin-1"))
                    conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass

    def close(self) -> None:
        self.server.close()


def _path_without_rg(tmp: Path) -> str:
    """A PATH with everything the VM's /usr/bin has but ``rg``: a host with no copy, whatever this host has."""
    farm = tmp / "no-rg-bin"
    farm.mkdir()
    for entry in os.scandir("/usr/bin"):
        if entry.name != "rg":
            (farm / entry.name).symlink_to(entry.path)
    return str(farm)


@pytest.fixture
def row(tmp_path, monkeypatch):
    """A register of the test's own with AEW's real shipped ripgrep record, no fetch, and a proxy."""
    monkeypatch.setattr(store, "ROOT_OVERRIDE", tmp_path / "register")
    proxy = LoggingProxy()
    yield proxy
    proxy.close()


def _plant_host(tmp: Path, *, on_path: str) -> tuple[Path, str]:
    """A host copy with ripgrep's shape, where a sandbox sees it (the home directory, not this test's /tmp)."""
    import atexit
    import tempfile

    directory = Path(tempfile.mkdtemp(prefix="aew-test-q08-", dir=Path.home()))
    atexit.register(shutil.rmtree, directory, True)
    real = shutil.which("rg")
    exe = directory / "rg"
    if real:  # the host's own, when it has one, so the search really works through it
        shutil.copy2(real, exe)
    else:
        exe.write_text('#!/bin/sh\ncase "$1" in --version) echo "ripgrep 9.9.9";; *) echo 3;; esac\n')
        exe.chmod(0o755)
    return exe, f"{directory}:{on_path}"


def _search(tmp: Path, proxy: LoggingProxy, monkeypatch: Any, path: str) -> dict[str, Any]:
    """The real route: establish, the adapter's server environment, a real server in the sandbox, one real search."""
    monkeypatch.setenv("PATH", path)
    project, worktree = tmp / "project", tmp / "worktree"
    for repo in (project, worktree):
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    run = tmp / "runs" / "R-1"
    run.parent.mkdir()
    scratch = run / "scratch"
    layout, label = C.establish(role="implementer", scope="ticket", workspace=str(worktree), run_dir=run,
                                scratch=str(scratch), bridge_dir=None,
                                policy={"containment": {"network": {"mode": "shared"}}}, project=str(project))
    assert layout is not None and label["self_test"]["ok"] is True
    state = run / "harness"
    base = {"PATH": path, "HOME": os.environ["HOME"], "LANG": "C.UTF-8", "HTTPS_PROXY": f"http://127.0.0.1:{proxy.port}",
            "HTTP_PROXY": f"http://127.0.0.1:{proxy.port}", "SHELL": "/bin/sh"}
    env = adapter.server_env(base, state, provider_env=[], config=projection.lead_config(),
                             password=os.urandom(16).hex())
    env.update({"HTTPS_PROXY": base["HTTPS_PROXY"], "HTTP_PROXY": base["HTTP_PROXY"]})
    tree = procs.ProcessTree(layout=layout)
    plain = tmp_dir = scratch / "plain"  # no repository: OpenCode searches here with ripgrep, not its own index
    tmp_dir.mkdir(parents=True)
    (plain / "needle.txt").write_text("hay\n")
    found: Any = None
    error: str | None = None
    try:
        server = Server.start(tree.spawn, adapter.binary_command(), env=env, cwd=str(worktree),
                              log_path=tmp / "server.log")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                found = server.client.get("/api/fs/find", {"location[directory]": str(plain), "query": "needle"})
                break
            except Exception as exc:  # noqa: BLE001  # the row reads its text: the search's failure is the subject
                error = f"{type(exc).__name__}: {exc}"
                if "503" not in error and "starting" not in error:
                    break
                time.sleep(0.5)
    finally:
        tree.kill()
        tree.close()
    log = (tmp / "server.log").read_text(encoding="utf-8", errors="replace") if (tmp / "server.log").exists() else ""
    return {"layout": layout, "label": label, "found": found, "error": error, "log": log,
            "bin": Path(env["XDG_CACHE_HOME"]) / "opencode" / "bin"}


def _nothing_was_downloaded(result: dict[str, Any], proxy: LoggingProxy) -> None:
    print("Q08-ROW", {"found": result["found"], "error": result["error"], "proxy": proxy.log, "bin": str(result["bin"]),
                      "log": [ln[:300] for ln in result["log"].splitlines() if "ripgrep" in ln.lower() or " rg" in ln]})
    held = sorted(p.name for p in result["bin"].rglob("*")) if result["bin"].exists() else []
    assert held == [], f"the server's own bin directory holds {held}"
    assert not [line for line in proxy.log if GITHUB in line], proxy.log
    assert "downloading ripgrep" not in result["log"]


REAL = "AEW_CAP1_REAL_DIR"  # a directory of the operator's choosing: naming it is what allows a real fetch, once


@pytest.fixture
def real() -> Path:
    if not os.environ.get(REAL):
        pytest.skip(f"a real fetch from github.com is the operator's to allow: set {REAL}")
    return Path(os.environ[REAL])


def test_the_operators_check_fetches_the_real_archive_and_aews_pinned_ripgrep_serves(row, real, tmp_path,
                                                                                     monkeypatch):
    """CAPR-X01, and CAPR-Q10 as the operator chooses it (the operator, 2026-11-05: AEW downloads no tool unless the
    operator chooses it): the real archive by the operator's `aew capability check`, checked against its pin;
    FUNCTIONAL_ONLY before the first use; a real server's search runs through it, and neither the launch nor OpenCode
    fetches anything. The register stays in that directory, so running this again fetches nothing, and the archive is
    kept for the next test."""
    monkeypatch.setattr(store, "ROOT_OVERRIDE", real / "register")
    fetched = P.fetch

    def keeping(pinned: dict[str, Any]) -> bytes:
        data = fetched(pinned)
        (real / Path(pinned["source"]).name).write_bytes(data)
        return data

    monkeypatch.setattr(P, "fetch", keeping)
    ops.check("ripgrep")
    monkeypatch.setattr(P, "fetch", lambda _p: pytest.fail("a launch fetched"))
    got = _search(tmp_path, row, monkeypatch, _path_without_rg(tmp_path))
    tool = got["label"]["self_test"]["tools"]["ripgrep"]
    assert tool["served"] == status.AEW_COPY and tool["tried"][0]["version"].startswith("ripgrep 15.1.0"), tool
    assert Path(got["layout"].tools_first, "rg").resolve() == Path(tool["path"])
    assert [e["path"] for e in got["found"]["data"]] == ["needle.txt"], got
    _nothing_was_downloaded(got, row)
    cap = next(c for c in ops.listing()["capabilities"] if c["id"] == "EXACT_CODE_SEARCH")
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["pinned"] is True and cap["version"] == "15.1.0"
    assert cap["limitations"] == [] and store.read()["checks"]["aew:ripgrep"]["where"] == status.IN_SANDBOX


def test_an_offline_host_imports_the_same_archive_and_its_check_runs_contained(real, tmp_path, monkeypatch):
    """CAPR-Q05, with the real archive the fetch above kept, no network, and the operator's change as the endpoint
    applies it. Its status comes from inside a sandbox (CAPR-13)."""
    from capability_stand_in import _principal

    monkeypatch.setattr(store, "ROOT_OVERRIDE", tmp_path / "offline")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: pytest.fail("the import reached the network"))
    pinned = records.shipped()["ripgrep"]["payloads"][records.platform_key()]
    archive = real / Path(pinned["source"]).name
    if not archive.exists():
        pytest.skip("the fetch's own test keeps the archive: run it first")
    ops.apply(_principal(), ops.preview(ops.IMPORT, {"path": str(archive)}))
    cap = next(c for c in ops.listing()["capabilities"] if c["id"] == "EXACT_CODE_SEARCH")
    assert cap["observed_status"] == status.FUNCTIONAL_ONLY and cap["pinned"] is True
    assert store.read()["checks"]["aew:ripgrep"]["where"] == status.IN_SANDBOX


def _plant_refused(tmp: Path) -> None:
    """A payload one byte off its pin, as a host holds it: a file at its own path, whatever else is there."""
    record = records.shipped()["ripgrep"]
    pinned = record["payloads"][records.platform_key()]
    path = P.path_of("ripgrep", record["command"], pinned)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"#!/bin/sh\nexit 0\n")
    path.chmod(0o500)


@pytest.mark.parametrize("payload", ["missing", "refused"])
def test_with_a_host_copy_nothing_is_downloaded_and_the_copy_is_named_unpinned(row, tmp_path, monkeypatch, payload):
    if payload == "refused":
        _plant_refused(tmp_path)
    host, path = _plant_host(tmp_path, on_path=_path_without_rg(tmp_path))
    got = _search(tmp_path, row, monkeypatch, path)
    tool = got["label"]["self_test"]["tools"]["ripgrep"]
    assert tool["served"] == status.HOST_COPY and tool["path"] == str(host.resolve())
    _nothing_was_downloaded(got, row)
    cap = next(c for c in ops.listing()["capabilities"] if c["id"] == "EXACT_CODE_SEARCH")
    assert cap["copy"] == status.HOST_COPY and cap["pinned"] is False and status.UNPINNED in cap["limitations"]
    assert ("does not match its pin" if payload == "refused" else "not on this host") in cap["cause"]
    if shutil.which("rg", path="/usr/bin"):  # with a real ripgrep to copy, the search really ran through the copy
        assert [e["path"] for e in got["found"]["data"]] == ["needle.txt"], got


def test_without_a_stub_the_same_row_shows_the_download_so_these_rows_can_see_one(row, tmp_path, monkeypatch):
    """The control: with the context's entry gone, a lookup misses, and OpenCode goes for its download. The proxy's log
    has the request, and the proxy refuses it, so nothing comes down. Rows that could not see this would prove
    nothing."""
    monkeypatch.setattr(bind, "_serve", lambda *_a, **_k: None)
    _search(tmp_path, row, monkeypatch, _path_without_rg(tmp_path))
    assert [line for line in row.log if GITHUB in line], row.log


@pytest.mark.parametrize("payload", ["missing", "refused"])
def test_with_no_copy_the_stubs_run_fails_nothing_is_downloaded_and_the_status_names_the_cause(
        row, tmp_path, monkeypatch, payload):
    """The row that matters most: a failing ``rg`` does not make OpenCode fall back to its download."""
    if payload == "refused":
        _plant_refused(tmp_path)
    got = _search(tmp_path, row, monkeypatch, _path_without_rg(tmp_path))
    assert got["label"]["self_test"]["tools"]["ripgrep"]["served"] is None
    assert not L.Path(got["layout"].tools_first, "rg").is_symlink()
    _nothing_was_downloaded(got, row)
    assert got["found"] is None and " 500" in (got["error"] or ""), got  # the search failed: the stub is what ran
    cap = next(c for c in ops.listing()["capabilities"] if c["id"] == "EXACT_CODE_SEARCH")
    wanted = status.REFUSED if payload == "refused" else status.UNAVAILABLE
    assert cap["observed_status"] == wanted and ("pin" if payload == "refused" else "not on this host") in cap["cause"]
    assert cap["fix"]
