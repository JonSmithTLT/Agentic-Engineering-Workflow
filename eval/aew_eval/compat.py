"""The M3 dogfood records (``aew/dogfood-run/v1``) as ``aew/eval-run/v1`` (design §3; completion criterion 1).

The mapping is deterministic and never rewrites a historical record: ``legacy.record`` holds the original exactly and
``legacy.sha256`` its canonical hash; every other field is derived from it. :data:`FIELDS` names, for every M3 field,
where its meaning lives in the new envelope, so a field the mapping does not account for fails the tests instead of
disappearing. The M3 run had no preregistration, assignment or validity verdict, so those stay null: the mapping
reports what was recorded and invents nothing.

    python -m aew_eval.compat eval/m3/dogfood/results.jsonl   # one aew/eval-run/v1 record per line, on stdout
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from aew_eval.canonical import sha256_of
from aew_eval.schemas import validate

LEGACY = "aew/dogfood-run/v1"
EXPERIMENT = "m3-dogfood"

# Every aew/dogfood-run/v1 field and where it is in aew/eval-run/v1 (``legacy.record`` always keeps the original).
FIELDS: dict[str, str] = {
    "schema": "legacy.schema",
    "task": "case.id",
    "mode": "arm.id and arm.kind",
    "model": "profile.requested.model",
    "routing": "profile.requested.routing",
    "title": "notes (the task's title)",
    "aew_commit": "aew.commit",
    "started_at": "started_at",
    "ended_at": "ended_at",
    "wall_s": "wall_s",
    "workdir": "environment.workdir",
    "agent_shell": "harness.agent_shell",
    "cap_usd": "limits.cap_usd",
    "limits": "limits",
    "revision": "aew_facts.revision",
    "units": "aew_facts.units",
    "invocations": "aew_facts.invocations",
    "runs": "aew_facts.runs",
    "reviews": "aew_facts.reviews",
    "verifications": "aew_facts.verifications",
    "lead": "aew_facts.lead",
    "lead_session": "aew_facts.lead_session",
    "lead_guide": "aew_facts.lead_guide",
    "stopped_runs": "aew_facts.stopped_runs",
    "setup": "aew_facts.setup",
    "raw": "outcome.raw",
    "hidden": "outcome.hidden",
    "integrated_commit": "outcome.integrated_commit",
    "changed_paths": "outcome.changed_paths",
    "out_of_scope": "outcome.out_of_scope",
    "interventions": "outcome.interventions",
    "safety": "outcome.safety",
    "totals": "cost (tokens and dollars) and outcome.reached_done, outcome.hidden_passed",
}
AEW_FACTS = ("revision", "units", "invocations", "runs", "reviews", "verifications", "lead", "lead_session",
             "lead_guide", "stopped_runs", "setup")


def run_id(record: dict[str, Any]) -> str:
    """Deterministic and unique: the task, the mode and the record's own hash."""
    return f"{EXPERIMENT}/{record['task']}-{record['mode']}-{sha256_of(record)[:12]}"


def from_dogfood(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema") != LEGACY:
        raise ValueError(f"not an {LEGACY} record: {record.get('schema')!r}")
    unknown = sorted(set(record) - set(FIELDS))
    if unknown:
        raise ValueError(f"M3 fields {unknown} have no place in the mapping; add them to compat.FIELDS")
    totals = record.get("totals") or {}
    mapped = {
        "schema": "aew/eval-run/v1",
        "experiment": EXPERIMENT,
        "preregistration_sha256": None,  # M3 had no preregistration
        "run_id": run_id(record),
        "case": {"id": record["task"], "sha256": None, "hidden_sha256": None},
        "arm": {"id": record["mode"], "kind": record["mode"], "config_sha256": None},
        "profile": {"requested": {"model": record.get("model"), "routing": record.get("routing")}, "observed": [],
                    "mismatch": None},
        "aew": {"commit": record.get("aew_commit")},
        "harness": {"name": "opencode", "agent_shell": record.get("agent_shell")},
        "environment": {"workdir": record.get("workdir")},
        "assignment": None,  # M3 runs were not scheduled from a seed
        "validity": None,  # M3 had no validity verdict; nothing is inferred
        "started_at": record.get("started_at"),
        "ended_at": record.get("ended_at"),
        "wall_s": record.get("wall_s"),
        "limits": {**(record.get("limits") or {}), "cap_usd": record.get("cap_usd")},
        "outcome": {
            "hidden": record.get("hidden"),
            "hidden_passed": totals.get("passed"),
            "reached_done": totals.get("done"),
            "integrated_commit": record.get("integrated_commit"),
            "changed_paths": record.get("changed_paths"),
            "out_of_scope": record.get("out_of_scope"),
            "interventions": record.get("interventions"),
            "safety": record.get("safety"),
            **({"raw": record["raw"]} if "raw" in record else {}),
        },
        "aew_facts": {k: record[k] for k in AEW_FACTS if k in record},
        "cost": {"provider_reported_usd": totals.get("cost_usd"), "derived_usd": totals.get("cost_from_tokens_usd"),
                 "tokens": totals.get("tokens"), "totals": totals},
        "notes": record.get("title"),
        "legacy": {"schema": LEGACY, "sha256": sha256_of(record), "record": record},
    }
    validate("aew/eval-run/v1", mapped, what=f"the mapping of {mapped['run_id']}")
    return mapped


def read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    for record in read(Path((argv or sys.argv[1:])[0])):
        print(json.dumps(from_dogfood(record), sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
