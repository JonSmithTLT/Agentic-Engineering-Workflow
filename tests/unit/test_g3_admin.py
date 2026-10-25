"""Root's administration commands and the service's start refusals (A-37 G3-01, G3-05, G3-09, G3-14; STG-03, G3-A).
Linux only: ``aew-g3`` refuses Windows, and its sockets are Unix filesystem sockets.

``set-pin`` and ``rotate-key`` run through ``cli.main`` as root runs them, with ``os.geteuid`` patched and ``getpass``
stubbed: nothing here needs root, and the PIN is a labelled stand-in (review of #269, M1 and m4).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew_g3 import COMMAND, ROOT, cli
from aew_g3.keys import KEY_FILE, RETIRED_DIR, KeyStore
from tests.helpers import g3 as G

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="aew-g3 runs on Linux only (A-37)")


@pytest.fixture(autouse=True)
def _no_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """getpass reads the terminal: a path that reaches it unstubbed fails at once rather than waiting for a PIN."""
    def refuse(prompt: str = "") -> str:
        raise AssertionError(f"getpass reached with no stubbed answer: {prompt!r}")

    monkeypatch.setattr(cli.getpass, "getpass", refuse)


def _pins(monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    it: Iterator[str] = iter(answers)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(it))


def _refusal(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().err.strip().splitlines()[-1])


def _inodes(d: Path) -> set[tuple[str, int]]:
    return {(p.relative_to(d).as_posix(), p.lstat().st_ino) for p in d.rglob("*")}


# ------------------------------------------------------------------------------------------------ M1 ownership
def test_set_pin_and_rotate_key_run_as_root_hand_everything_they_write_to_the_state_directorys_owner(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Every file and directory either command creates in the state directory is chowned to the directory's owner, the
    service's dynamic UID: systemd's StateDirectory= set-up does not descend to fix them (review of #269, M1)."""
    state = tmp_path / "state"
    state.mkdir()
    old = KeyStore(state).key_id  # the service made its key at its first start
    owner = (state.stat().st_uid, state.stat().st_gid)
    chowned: dict[int, tuple[int, int]] = {}
    real_chown = os.chown

    def chown(p: str | Path, uid: int, gid: int) -> None:
        chowned[os.lstat(p).st_ino] = (uid, gid)
        real_chown(p, uid, gid)  # to the caller's own IDs: allowed without root

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", chown)
    for argv, answers in ((["set-pin"], (G.PIN, G.PIN)), (["rotate-key"], ())):
        before = _inodes(state)
        _pins(monkeypatch, *answers)
        assert cli.main([*argv, "--state-dir", str(state)]) == 0, capsys.readouterr().err
        written = _inodes(state) - before
        assert written, argv  # control: the command wrote something
        assert {name: chowned.get(ino) for name, ino in written} == {name: owner for name, _ in written}, argv
    assert {p.relative_to(state).as_posix() for p in state.rglob("*")} >= \
        {"pin.json", KEY_FILE, RETIRED_DIR, f"{RETIRED_DIR}/{old}.pub"}
    assert KeyStore(state).key_id != old and old in KeyStore(state).public_pems()
    assert G.PIN not in capsys.readouterr().out


def test_as_any_other_caller_the_files_are_already_the_callers_and_nothing_is_chowned(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The control of the test above: the service itself and the tests run as the state directory's owner."""
    from aew_g3 import deployment, keys, pinstore

    state = tmp_path / "state"
    state.mkdir()
    calls: list[object] = []
    monkeypatch.setattr(os, "geteuid", lambda: 4242)
    monkeypatch.setattr(os, "chown", lambda *a: calls.append(a))
    pinstore.set_pin(state, G.PIN, deployment.Deployment(**G.shipped_values()))
    KeyStore(state)
    keys.rotate(state)
    assert calls == []


# ------------------------------------------------------------------------------------------------ m4 refusals
def test_the_administration_commands_refuse_a_caller_that_is_not_root_or_a_missing_state_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(os, "geteuid", lambda: 4242)
    for command in ("set-pin", "rotate-key"):
        _pins(monkeypatch, G.PIN, G.PIN)  # what a caller let past the check would be asked
        assert cli.main([command, "--state-dir", str(state)]) != 0
        out = _refusal(capsys)
        assert (out["code"], out["details"]["reason"]) == ("PERMISSION_DENIED", "NOT_ROOT"), command
        assert f"sudo {COMMAND} {command}" in str(out["message"]), out
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    for command in ("set-pin", "rotate-key"):
        _pins(monkeypatch, G.PIN, G.PIN)
        assert cli.main([command, "--state-dir", str(tmp_path / "absent")]) != 0
        assert _refusal(capsys)["details"]["reason"] == "NO_STATE_DIR", command
    assert list(state.iterdir()) == [] and not (tmp_path / "absent").exists()


def test_set_pin_refuses_two_different_pins_and_changes_nothing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    _pins(monkeypatch, G.PIN, G.PIN + "x")
    assert cli.main(["set-pin", "--state-dir", str(state)]) != 0
    assert _refusal(capsys)["details"]["reason"] == "PIN_MISMATCH"
    assert list(state.iterdir()) == []
    _pins(monkeypatch, G.PIN, G.PIN)  # control: the same PIN twice is set
    assert cli.main(["set-pin", "--state-dir", str(state)]) == 0
    assert (state / "pin.json").is_file()


@pytest.mark.parametrize("content", [None, "not-a-machine-id\n"], ids=["missing", "malformed"])
def test_serve_refuses_to_start_with_no_machine_id_to_derive_its_issuer_from(
        tmp_path: Path, content: str | None) -> None:
    """In its own process: serve lowers its core limit to zero first, which no process can raise again."""
    machine_id = tmp_path / "machine-id"
    if content is not None:
        machine_id.write_bytes(content.encode())
    code = ("import sys; sys.path[:0] = sys.argv[1:3]\n"
            "from pathlib import Path\n"
            "from aew_g3 import cli\n"
            "cli.MACHINE_ID = Path(sys.argv[3])\n"
            "sys.exit(cli.main(['serve', '--state-dir', sys.argv[4], '--runtime-dir', sys.argv[5]]))\n")
    run = subprocess.run([sys.executable, "-I", "-c", code, str(G.REPO / "src"), str(ROOT), str(machine_id),
                          str(tmp_path), str(tmp_path / "run")], capture_output=True, text=True, timeout=60)
    assert run.returncode != 0
    assert json.loads(run.stderr.strip().splitlines()[-1])["details"]["reason"] == "NO_MACHINE_ID", run.stderr
    assert not (tmp_path / "run").exists(), "it never listened"


# ------------------------------------------------------------------------------------------------ G3-10 the peer
def test_the_peers_uid_is_read_unsigned_so_an_operator_uid_of_2_31_or_more_is_still_the_operators() -> None:
    """struct ucred is (pid_t, uid_t, gid_t): only the pid is signed (review of #269, m6)."""
    import socket
    import struct

    from aew_g3 import server

    class Conn:
        def getsockopt(self, *_: object) -> bytes:
            return struct.pack("iII", 4242, 2**31 + 7, 2**32 - 2)

    assert server.peer_uid(Conn()) == 2**31 + 7  # type: ignore[arg-type]
    a, b = socket.socketpair(socket.AF_UNIX)
    try:
        assert server.peer_uid(a) == os.getuid()  # control: a real peer
    finally:
        a.close()
        b.close()


# ------------------------------------------------------------------------------------------------ G3-01 the sockets
def test_the_service_starts_only_on_both_sockets_owned_by_one_account_that_is_not_root(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator is the sockets' owner (SocketUser=): both must be there, agree, and not be root's (G3-01; review of
    #269, m4 B7)."""
    from aew.errors import ValidationFailed
    from aew_g3 import server

    socks = server.bind_sockets(tmp_path / "run")
    try:
        assert server.operator_uid_of(socks) == os.getuid()  # control
        with pytest.raises(ValidationFailed) as e:
            server.operator_uid_of({server.REQUEST_SOCK: socks[server.REQUEST_SOCK]})
        assert e.value.details["reason"] == "SOCKETS_MISSING"
        real_stat = os.stat
        for owners in ((0, 0), (os.getuid(), os.getuid() + 1)):
            by_path = dict(zip((socks[k].getsockname() for k in (server.REQUEST_SOCK, server.CONFIRM_SOCK)), owners,
                               strict=True))
            monkeypatch.setattr(os, "stat", lambda p, *a, by_path=by_path, **k: SimpleNamespace(st_uid=by_path[p])
                                if p in by_path else real_stat(p, *a, **k))
            with pytest.raises(ValidationFailed) as e:
                server.operator_uid_of(socks)
            assert e.value.details["reason"] == "SOCKET_OWNER", owners
            monkeypatch.undo()
    finally:
        for s in socks.values():
            s.close()


def test_a_socket_systemd_passes_that_is_not_a_filesystem_unix_socket_stops_the_service(tmp_path: Path) -> None:
    """An abstract socket has no file mode and no owner to name the operator (G3-01): refused at start. The control
    passes a filesystem socket the same way. Each runs in its own process: descriptor 3 is systemd's slot."""
    code = ("import json, os, socket, sys; sys.path[:0] = sys.argv[1:3]\n"
            "from aew.errors import ValidationFailed\n"
            "from aew_g3 import server\n"
            "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            "s.bind(sys.argv[3] if sys.argv[3].startswith('/') else '\\0' + sys.argv[3])\n"
            "os.dup2(s.fileno(), 3)\n"
            "os.environ.update(LISTEN_FDS='1', LISTEN_PID=str(os.getpid()))\n"
            "try:\n"
            "    print(json.dumps(sorted(server.activated_sockets())))\n"
            "except ValidationFailed as e:\n"
            "    print(json.dumps(e.details['reason']))\n")
    out = {}
    for label, name in (("abstract", f"aew-g3-test-{os.getpid()}"), ("filesystem", str(tmp_path / "request.sock"))):
        run = subprocess.run([sys.executable, "-I", "-c", code, str(G.REPO / "src"), str(ROOT), name],
                             capture_output=True, text=True, timeout=60, check=True)
        out[label] = json.loads(run.stdout)
    assert out == {"abstract": "SOCKET_NOT_FILESYSTEM", "filesystem": ["request.sock"]}
