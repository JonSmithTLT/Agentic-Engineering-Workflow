"""Host-owned evidence for O-02. An outage read only observes or checks it."""

from __future__ import annotations

import hashlib
import json
import platform
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aew
from aew import hoststate
from aew.stg02 import wire

GATE = tuple(f"O02-Q{i:02}" for i in range(1, 9))
SCHEMA = "aew/o02-host-qualification/v1"


def g3_present() -> bool:
    """Presence only: G3's service and client records are never opened by the outage reader."""
    from aew import g3client, g3standing

    return any(path.exists() for path in (Path(g3client.REQUEST_SOCK), Path(g3standing.CONFIRMER),
                                          g3client.approval_records_dir()))


def record_path() -> Path:
    return hoststate.root() / "g4" / "qualification.json"


def binding() -> dict[str, str]:
    """Identify the installed reader and Linux host without reading any project or contacting a service."""
    package = Path(aew.__file__).resolve().parent
    release = hashlib.sha256()
    for path in sorted(p for p in package.rglob("*") if p.suffix in {".py", ".json", ".yaml"} and p.is_file()):
        release.update(path.relative_to(package).as_posix().encode())
        release.update(b"\0")
        release.update(hashlib.sha256(path.read_bytes()).digest())
    machine_id = Path("/etc/machine-id").read_bytes().strip()
    if not machine_id:
        raise ValueError("the host has no machine ID")
    host = hashlib.sha256(machine_id + b"\0" + platform.release().encode() + b"\0" + platform.machine().encode())
    return {"aew_version": aew.__version__, "d01_version": wire.D01_VERSION, "reader_sha256": release.hexdigest(),
            "host_sha256": host.hexdigest()}


def record_template() -> dict[str, Any]:
    """Prepare the shape and actual binding for the operator's gate evidence, without writing a record."""
    return {"schema": SCHEMA, "subject": "aew read", "binding": binding(), "profile": "",
            "harness_version": "", "provider_version": "", "permitted_operations": ["D-01 O-02 outage read"],
            "applicability": "", "evidence_issuer": "", "tested_at": "", "valid_until": "", "invalidation_triggers": [],
            "containment_evidence": "", "checks": dict.fromkeys(GATE, "")}


def qualified() -> bool:
    """A current operator-held record counts solely for the Linux release and host the operator qualified."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        path = record_path()
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024:
            return False
        record = json.loads(path.read_bytes())
        if not isinstance(record, dict) or record.get("schema") != SCHEMA or record.get("subject") != "aew read":
            return False
        if any(not isinstance(record.get(field), str) or not record[field].strip()
               for field in ("profile", "harness_version", "provider_version", "applicability", "evidence_issuer",
                             "containment_evidence")):
            return False
        if not all(isinstance(record.get(field), list) and record[field]
                   and all(isinstance(entry, str) and entry for entry in record[field])
                   for field in ("permitted_operations", "invalidation_triggers")):
            return False
        checks = record.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(GATE):
            return False
        if any(not isinstance(evidence, str) or not evidence.strip() for evidence in checks.values()):
            return False
        return (wire.parse_time(record["tested_at"]) <= datetime.now(UTC) < wire.parse_time(record["valid_until"])
                and record.get("binding") == binding())
    except (OSError, TypeError, ValueError, KeyError, RecursionError):
        return False
