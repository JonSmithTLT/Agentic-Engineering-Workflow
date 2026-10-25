"""The operator's PIN, kept only as a salted scrypt hash in the service's state directory (G3-05).

Root sets and resets it (``sudo /usr/local/sbin/aew-g3 set-pin``). Each set writes a new record with a fresh random
``pin_id``: the lockout count is kept in the durable ledger against that id, so setting the PIN is what ends a lockout
(G3-05, "until root resets the PIN"), and a restart never does (G3-11). The record also keeps the minimum length the
PIN was set under, so a raised minimum locks a PIN set under a lower one until root sets a new one.

The service reads the record at each approval, never once at start: a record that cannot be read holds the approval
(G3-11), and a PIN root has just set takes effect at once.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.errors import ValidationFailed

from .deployment import Deployment, pin_max_length
from .ownership import hand_to_service

PIN_FILE = "pin.json"
# scrypt at 2^15 x 8 x 1 (32 MiB): the standard library's memory-hard function at a common interactive setting. The
# parameters live in each record, so a later change rehashes at the next set-pin without breaking the current PIN.
SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1}
_MAXMEM = 64 * 1024 * 1024


class PinUnavailable(Exception):
    """The PIN record cannot be read or is not well formed: every approval is held (G3-11)."""


@dataclass(frozen=True)
class PinRecord:
    pin_id: str
    salt: bytes
    digest: bytes
    n: int
    r: int
    p: int
    min_length: int

    def matches(self, pin: str) -> bool:
        """Compares in constant time (G3-05)."""
        return hmac.compare_digest(_hash(pin, self.salt, self.n, self.r, self.p), self.digest)


def _hash(pin: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=32)


def read(state_dir: Path) -> PinRecord:
    try:
        raw: dict[str, Any] = json.loads((state_dir / PIN_FILE).read_bytes().decode("utf-8"))
        return PinRecord(pin_id=str(raw["pin_id"]), salt=base64.b64decode(raw["salt"]),
                         digest=base64.b64decode(raw["hash"]), n=int(raw["n"]), r=int(raw["r"]), p=int(raw["p"]),
                         min_length=int(raw["min_length"]))
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise PinUnavailable(type(e).__name__) from None


def set_pin(state_dir: Path, pin: str, deployment: Deployment) -> str:
    """Writes a new PIN record and returns its ``pin_id``. The PIN itself is never stored, logged or returned."""
    if len(pin) < deployment.pin_min_length or len(pin) > pin_max_length():
        raise ValidationFailed(f"the PIN must be {deployment.pin_min_length} to {pin_max_length()} characters (the "
                               "deployment's minimum, and the longest the confirmer can send); nothing was changed",
                               reason="PIN_LENGTH", minimum=deployment.pin_min_length, maximum=pin_max_length())
    salt = secrets.token_bytes(16)
    pin_id = secrets.token_hex(16)
    record = {"pin_id": pin_id, "salt": base64.b64encode(salt).decode("ascii"),
              "hash": base64.b64encode(_hash(pin, salt, **SCRYPT)).decode("ascii"), **SCRYPT,
              "min_length": deployment.pin_min_length}
    target = state_dir / PIN_FILE
    tmp = state_dir / (PIN_FILE + ".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(record, sort_keys=True).encode("ascii"))
        os.fsync(fd)
    finally:
        os.close(fd)
    hand_to_service(state_dir, tmp)  # root's file is the service account's, never root's (G3-05)
    os.replace(tmp, target)
    return pin_id
