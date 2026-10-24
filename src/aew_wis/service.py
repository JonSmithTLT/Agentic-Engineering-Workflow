"""The issuer's process under systemd (WIS-01, WIS-09): ``aew-wis-issuer@<instance>.service``, one per store.

**Its paths** follow from the instance name, the 32 hex characters of the store's ``store_ref`` (WIS-01; the unit
templates in ``aew_wis/units``):

* root's anchor, ``/etc/aew-wis/<instance>/anchor.json`` (WIS-11), owned by root on a root-owned path;
* the view: the store's ``.aew/state`` bound read-only at ``/run/aew-wis-view/<instance>/state`` by the store-path
  drop-in, so ``/run/aew-wis-view/<instance>`` is an AEW root to the engine's own path rules;
* its state, the ``StateDirectory`` ``/var/lib/aew-wis/<instance>``: the held state, its key and its public keys;
* its published keys, ``/run/aew-wis/<instance>/keys/<key_id>.pub``;
* the witness, ``/run/aew-wis/<instance>/witness.sock``, created by ``aew-wis-witness@<instance>.socket`` and passed in
  by systemd (``LISTEN_FDS``).

**When it reads:** at start, on an inotify ``IN_MOVED_TO`` in the bound ``state/`` (``control.yaml`` is replaced by
rename), and at least every read interval; every read runs all of WIS-02's checks. **It exits with status 0** when it
has run the view's age, and systemd restarts it (``Restart=always``), which sets its view up again from the store's
path; ``RuntimeMaxSec=`` is only the backstop. **On a stop signal** it attests nothing more and exits.

**The operator** whose UID alone may use the witness (``SO_PEERCRED``) is read from root's configuration, never from a
setting: the owner of ``witness.sock`` (``SocketUser=``) and the owner of the bound store directory must be the same
UID, neither root nor the service's own, or the issuer refuses to start.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import re
import select
import signal
import socket
import struct
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew_wis import keys as K
from aew_wis import wire as W
from aew_wis.engine_rules import canonical_json
from aew_wis.identity import Identity, view_identity
from aew_wis.issuer import AnchorRefused, Issuer, read_root_file, write_atomically

IN_MOVED_TO = 0x00000080
IN_NONBLOCK = 0o4000
IN_CLOEXEC = 0o2000000
REQUEST_MAX = 8192
CLIENT_TIMEOUT_S = 1.0
_ROUTE = re.compile(rb"GET /wis/v1/attestations/(proof:wis:[0-9a-f]{32}) HTTP/1\.[01]")
_REASONS = {200: "OK", 403: "Forbidden", 404: "Not Found", 503: "Service Unavailable"}


class Refused(Exception):
    """The issuer will not start: the message says what is wrong. It exits non-zero and attests nothing."""


@dataclass(frozen=True)
class Paths:
    anchor: Path
    view_root: Path
    state: Path
    keys: Path
    socket: Path

    @classmethod
    def of(cls, instance: str) -> Paths:
        return cls(anchor=Path(f"/etc/aew-wis/{instance}/anchor.json"), view_root=Path(f"/run/aew-wis-view/{instance}"),
                   state=Path(f"/var/lib/aew-wis/{instance}"), keys=Path(f"/run/aew-wis/{instance}/keys"),
                   socket=Path(f"/run/aew-wis/{instance}/witness.sock"))


class LinuxView:
    """The bound store directory as the kernel shows it to this process."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def probe(self) -> tuple[Identity, int]:
        return view_identity(str(self.root / "state"))


def log(message: str) -> None:
    print(f"aew-wis: {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------- start-up

def passed_socket(env: dict[str, str] | None = None) -> socket.socket:
    """The listening witness socket systemd passed (``sd_listen_fds``): exactly one, a Unix stream socket."""
    env = dict(os.environ) if env is None else env
    if env.get("LISTEN_PID") != str(os.getpid()) or env.get("LISTEN_FDS") != "1":
        raise Refused("systemd passed no witness socket (LISTEN_FDS): start aew-wis-witness@<instance>.socket")
    sock = socket.socket(fileno=3)
    if sock.family != socket.AF_UNIX or sock.type != socket.SOCK_STREAM:
        raise Refused("the passed socket is not a Unix stream socket")
    for name in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"):
        os.environ.pop(name, None)  # never inherited by a child process
    sock.set_inheritable(False)
    return sock


def operator_uid(socket_path: Path, store_owner: int) -> int:
    """WIS-09's operator: ``witness.sock``'s owner (root's ``SocketUser=``), which must own the store too."""
    try:
        sock_owner = os.lstat(socket_path).st_uid
    except OSError as exc:
        raise Refused(f"{socket_path}: {exc.strerror}") from None
    own = os.getuid()  # type: ignore[attr-defined]
    if sock_owner != store_owner or sock_owner in (0, own):
        raise Refused(f"the witness socket is owned by UID {sock_owner} and the store by UID {store_owner}: they must be "
                      "the operator's, the same UID, neither root nor this service's")
    return sock_owner


def publish_keys(state: Path, keys_dir: Path) -> list[str]:
    """Every public key the issuer has used, read-only in its runtime directory (WIS-09). systemd makes that
    directory afresh at each start (the unit preserves nothing across a restart: WIS-A finding F-4), so this runs at
    each start, before the first request."""
    published = []
    for key_id, pem in K.recorded_publics(state).items():
        path = keys_dir / f"{key_id}.pub"
        if not (path.exists() and path.read_bytes() == pem):
            write_atomically(path, pem)
            os.chmod(path, 0o444)
        published.append(key_id)
    return published


def load_anchor(path: Path) -> dict[str, Any]:
    try:
        return json.loads(read_root_file(path))
    except FileNotFoundError:
        raise Refused(f"no anchor at {path}: root anchors the store at the console (WIS-11)") from None
    except (OSError, ValueError) as exc:
        raise Refused(f"{path}: {exc}") from None


# ---------------------------------------------------------------------------------------------- inotify

class Inotify:
    """``IN_MOVED_TO`` on one directory, non-blocking. A missed event only delays a read to the next poll."""

    def __init__(self, directory: Path) -> None:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        self.fd = libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1")
        if libc.inotify_add_watch(self.fd, os.fsencode(directory), IN_MOVED_TO) < 0:
            err = ctypes.get_errno()
            os.close(self.fd)
            raise OSError(err, f"inotify_add_watch {directory}")

    def drain(self) -> None:
        try:
            while os.read(self.fd, 65536):
                pass
        except BlockingIOError:
            pass


# ---------------------------------------------------------------------------------------------- the witness

def peer_uid(conn: socket.socket) -> int:
    _pid, uid, _gid = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    return uid


def answer(issuer: Issuer, conn: socket.socket, operator: int, now: datetime) -> int:
    """One request on one connection, then close: the peer's UID first, then the one route (WIS-09). Anything that is
    not ``GET /wis/v1/attestations/{proof_ref}`` is ``NOT_FOUND``. The status sent is returned."""
    conn.settimeout(CLIENT_TIMEOUT_S)
    try:
        uid = peer_uid(conn)
        data = b""
        if uid == operator:
            while b"\r\n" not in data and len(data) < REQUEST_MAX:
                chunk = conn.recv(REQUEST_MAX - len(data))
                if not chunk:
                    break
                data += chunk
        match = _ROUTE.fullmatch(data.split(b"\r\n", 1)[0])
        status, body = issuer.witness(match.group(1).decode() if match else "", uid, operator, now)
        payload = canonical_json(body)
        conn.sendall(f"HTTP/1.1 {status} {_REASONS[status]}\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload)
        return status
    except OSError:
        return 0  # the peer went away or was too slow: nothing was served
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------- the loop

class Service:
    def __init__(self, issuer: Issuer, listener: socket.socket, operator: int, watch: Inotify | None,
                 tripwires: W.Tripwires, clock: Any = None, monotonic: Any = time.monotonic) -> None:
        self.issuer, self.listener, self.operator, self.watch = issuer, listener, operator, watch
        self.tripwires = tripwires
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.stop_r, self.stop_w = os.pipe()
        os.set_blocking(self.stop_w, False)

    def stop(self, *_: Any) -> None:
        """The stop signal: nothing more is attested from here (WIS-01), and the loop ends."""
        self.issuer.stopping = True
        try:
            os.write(self.stop_w, b"x")
        except OSError:
            pass

    def run(self) -> int:
        started = self.monotonic()
        next_read = started
        last = None
        while not self.issuer.stopping:
            now_m = self.monotonic()
            if now_m - started >= self.tripwires.view_age:
                log(f"exiting after {self.tripwires.view_age} s, so systemd sets the view up again (WIS-01)")
                return 0
            if now_m >= next_read:
                outcome = self.issuer.read(self.clock())
                if outcome != last:
                    head = self.issuer.head
                    log(f"read {outcome}: head {head['state']} at revision {head['revision']}")
                    last = outcome
                gap = self.issuer.gap_age(self.clock())
                if gap is not None and gap.total_seconds() >= 3600:
                    log("REVISION_GAP has persisted for an hour: a reason for root to re-anchor (WIS-02, WIS-11)")
                next_read = self.monotonic() + self.tripwires.read_interval
            wait = max(0.0, min(next_read, started + self.tripwires.view_age) - self.monotonic())
            fds = [self.listener, self.stop_r] + ([self.watch.fd] if self.watch else [])
            ready, _, _ = select.select(fds, [], [], wait)
            if self.stop_r in ready or self.issuer.stopping:
                break
            if self.watch is not None and self.watch.fd in ready:
                self.watch.drain()
                next_read = self.monotonic()  # a commit was published: read now
            if self.listener in ready:
                try:
                    conn, _ = self.listener.accept()
                except OSError:
                    continue
                answer(self.issuer, conn, self.operator, self.clock())
        log("stopping: nothing more is attested")
        return 0


def tripwires_from(args: list[str]) -> W.Tripwires:
    names = {"--read-interval": "read_interval", "--renew-before": "renew_before", "--validity": "validity",
             "--view-age": "view_age", "--runtime-max": "runtime_max"}
    values: dict[str, int] = {}
    it = iter(args)
    for arg in it:
        if arg not in names:
            raise Refused(f"unknown argument {arg!r}")
        raw = next(it, None)
        if raw is None or not raw.isdigit():
            raise Refused(f"{arg} takes a whole number of seconds")
        values[names[arg]] = int(raw)
    t = W.Tripwires(**values)
    problems = t.problems()
    if problems:
        raise Refused("; ".join(problems))
    return t


def serve(instance: str, args: list[str], paths: Paths | None = None) -> int:
    """``serve <instance> [--read-interval S] [--renew-before S] [--validity S] [--view-age S] [--runtime-max S]``."""
    try:
        tripwires = tripwires_from(args)
        paths = paths or Paths.of(instance)
        anchor = load_anchor(paths.anchor)
        listener = passed_socket()
        view = LinuxView(paths.view_root)
        try:
            _ident, store_owner = view.probe()
        except OSError as exc:
            raise Refused(f"the bound store at {paths.view_root / 'state'} cannot be read: {exc}") from None
        operator = operator_uid(paths.socket, store_owner)
        signer = K.load_signer(paths.state)
        published = publish_keys(paths.state, paths.keys)
        issuer = Issuer(instance=instance, anchor=anchor, view=view, state_dir=paths.state, signer=signer,
                        tripwires=tripwires)
    except (Refused, AnchorRefused, K.KeyUnavailable) as exc:
        log(f"refusing to start: {exc}")
        return 2
    log(f"store {issuer.store_ref}, epoch {issuer.wis_epoch}, key {signer.key_id} ({len(published)} public key(s) "
        f"published), operator UID {operator}")
    service = Service(issuer, listener, operator, Inotify(paths.view_root / "state"), tripwires)
    signal.signal(signal.SIGTERM, service.stop)
    signal.signal(signal.SIGINT, service.stop)
    return service.run()
