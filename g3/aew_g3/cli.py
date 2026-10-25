"""``aew-g3``: the service (``serve``, run by systemd) and root's two administration commands (``set-pin``,
``rotate-key``). Linux only: G3 is a Linux profile (A-37).

The deployment values come only from the install root's ``etc/deployment.json`` (G3-14). ``--state-dir`` and
``--runtime-dir`` name where systemd put the service's own directories; under ``DynamicUser=`` with
``ProtectSystem=strict``, nothing else is writable to the service whatever they say.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import signal
import sys
import threading
from pathlib import Path

from aew.errors import AEWError, PermissionDenied, UsageError, ValidationFailed

from . import DEPLOYMENT_FILE, deployment, keys, pinstore

# The command root runs: install.sh writes it there (WRAPPER=), and sudo needs the full path on Rocky 8.
COMMAND = "/usr/local/sbin/aew-g3"
STATE_DIR = Path("/var/lib/aew-g3")  # StateDirectory=aew-g3 (systemd 239 sets no $STATE_DIRECTORY)
RUNTIME_DIR = Path("/run/aew-g3")
MACHINE_ID = Path("/etc/machine-id")


def _require_root(what: str) -> None:
    assert sys.platform != "win32"  # main() refuses Windows first
    if os.geteuid() != 0:
        raise PermissionDenied(f"{what} is root's administration (A-37 G3-05, G3-09): run sudo {COMMAND} {what}",
                               reason="NOT_ROOT")


def _state_dir(args: argparse.Namespace) -> Path:
    d = Path(args.state_dir)
    if not d.is_dir():
        raise ValidationFailed(f"{d} does not exist: start aew-g3.service once, so systemd creates the service's "
                               "state directory, then run this again", reason="NO_STATE_DIR", path=str(d))
    return d


def serve(args: argparse.Namespace) -> int:
    assert sys.platform != "win32"  # main() refuses Windows first
    import resource

    from . import server
    from .ledger import Ledger
    from .service import G3Service, issuer_ref_from_machine_id

    os.umask(0o077)  # the key, the PIN hash and the ledger are the service account's alone (G3-05, G3-09)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # no core dump ever holds a PIN; the unit sets LimitCORE=0 too
    dep = deployment.load(DEPLOYMENT_FILE)
    try:
        issuer_ref = issuer_ref_from_machine_id(MACHINE_ID.read_text(encoding="ascii"))
    except (OSError, ValueError):
        raise ValidationFailed(f"{MACHINE_ID} cannot be read, so the service has no issuer identity",
                               reason="NO_MACHINE_ID") from None
    state_dir = _state_dir(args)
    runtime_dir = Path(args.runtime_dir)
    socks = server.activated_sockets() or server.bind_sockets(runtime_dir)
    ledger = Ledger(state_dir)
    keystore = keys.KeyStore(state_dir)
    keystore.publish(runtime_dir / "keys", issuer_ref)
    srv = server.G3Server(G3Service(dep, state_dir, ledger, keystore, issuer_ref=issuer_ref), socks)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    srv.start()
    sys.stderr.write(f"aew-g3: ready key_id={keystore.key_id} operator_uid={srv.operator_uid} "
                     f"issuer_ref={issuer_ref}\n")
    sys.stderr.flush()
    stop.wait()
    srv.stop()
    ledger.close()
    return 0


def set_pin(args: argparse.Namespace) -> int:
    _require_root("set-pin")
    dep = deployment.load(DEPLOYMENT_FILE)
    state_dir = _state_dir(args)
    first = getpass.getpass("New G3 PIN: ")
    if getpass.getpass("The same PIN again: ") != first:
        raise ValidationFailed("the two PINs differ; nothing was changed", reason="PIN_MISMATCH")
    pinstore.set_pin(state_dir, first, dep)
    print("The G3 PIN is set. Approvals use it at once, and any lockout is over.")
    return 0


def rotate_key(args: argparse.Namespace) -> int:
    _require_root("rotate-key")
    old, new = keys.rotate(_state_dir(args))
    print(f"Retired key {old}; the new key is {new}. Restart aew-g3.service to sign with it. Records under the "
          "retired key stay verifiable from its published public key, and are no longer consumable.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aew-g3", description="AEW's G3 approval service (A-37).")
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn, text in (("serve", serve, "run the service (systemd starts it)"),
                           ("set-pin", set_pin, "set or reset the operator's PIN (root)"),
                           ("rotate-key", rotate_key, "retire the signing key and make a new one (root)")):
        s = sub.add_parser(name, help=text)
        s.add_argument("--state-dir", default=str(STATE_DIR))
        if name == "serve":
            s.add_argument("--runtime-dir", default=str(RUNTIME_DIR))
        s.set_defaults(fn=fn)
    return p


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        sys.stderr.write(json.dumps(UsageError("aew-g3 runs on Linux only (A-37)").to_dict()) + "\n")
        return 2
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except AEWError as e:
        sys.stderr.write(json.dumps(e.to_dict()) + "\n")
        return e.exit_code
