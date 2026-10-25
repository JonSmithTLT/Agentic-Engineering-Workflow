"""The deployment file (G3-14): four values, each checked against its tripwire at start, never clamped.

A-37 sets each limit as a tripwire, not a measured value, and the deployment may only tighten it: a shorter approval
expiry (G3-02) or consent validity (G3-06), a higher PIN minimum or a lower lockout count (G3-05). A value that is
missing, not a positive integer, beyond its limit, or a key the profile does not name stops the service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.errors import ValidationFailed

from . import wire

# key -> (which way it may move, A-37's limit)
TRIPWIRES: dict[str, tuple[str, int]] = {
    "approval_expiry_minutes": ("max", 10),   # G3-02
    "consent_validity_minutes": ("max", 15),  # G3-06
    "pin_min_length": ("min", 6),             # G3-05
    "lockout_after": ("max", 5),              # G3-05
}


def pin_max_length() -> int:
    """The longest PIN the confirmer can send: the wire's ``ApprovalDecision.pin.maxLength``."""
    return wire.schema()["$defs"]["ApprovalDecision"]["properties"]["pin"]["maxLength"]


@dataclass(frozen=True)
class Deployment:
    approval_expiry_minutes: int
    consent_validity_minutes: int
    pin_min_length: int
    lockout_after: int


def deployment_errors(values: Any) -> list[str]:
    """Every reason the values cannot start the service, as ``REASON:key``; empty when they can."""
    if not isinstance(values, dict):
        return ["NOT_AN_OBJECT:deployment"]
    errs = [f"UNKNOWN:{k}" for k in sorted(values) if k not in TRIPWIRES]
    for key, (kind, limit) in sorted(TRIPWIRES.items()):
        v = values.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            errs.append(f"MISSING:{key}")
        elif v > limit if kind == "max" else v < limit:
            errs.append(f"BEYOND_TRIPWIRE:{key}")
        elif key == "pin_min_length" and v > pin_max_length():
            errs.append(f"BEYOND_WIRE:{key}")  # no PIN that long could ever be sent, so no PIN could ever approve
    return errs


def load(path: Path) -> Deployment:
    try:
        values = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise ValidationFailed(f"the deployment file {path} cannot be read: {type(e).__name__}",
                               reason="DEPLOYMENT_UNREADABLE", path=str(path)) from None
    errs = deployment_errors(values)
    if errs:
        raise ValidationFailed(f"the G3 service will not start on {path}: {', '.join(errs)}. Each value must be "
                               "present and within its tripwire (A-37, G3-14); root corrects the file.",
                               reason="DEPLOYMENT_INVALID", path=str(path), errors=errs)
    return Deployment(**{k: values[k] for k in TRIPWIRES})
