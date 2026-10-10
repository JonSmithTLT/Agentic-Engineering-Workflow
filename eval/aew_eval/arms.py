"""Arms: how a case is run (evaluation component design v0.2, §2; decision 2).

An arm takes the built scratch repository and does the case's work in it; the runner does everything around it
(registration, the fixture, collection, finalization). Three kinds exist in the schemas:

* ``scripted``: no model and no provider. Its configuration is the exact edits to make, so a scripted cell is fully
  deterministic: the reference solution, a known-bad control, or the instrument's own end-to-end test.
* ``raw``: the harness alone. OpenCode's own ``build`` agent, the pinned model, the case's ``task`` as its only
  message, nobody answering: the M3 raw mode (``eval/m3/dogfood/dogfood.py --mode raw``), generalized. It drives
  OpenCode through the M3 driver's headless session (``eval/m3/dogfood/headless.py``, reused rather than copied, so
  a raw run here is the M3 raw baseline: a private server and private state, the provider variables only in the
  server's environment, a curated shell environment, every permission request or form rejected). Its session
  database is kept with the run's scratch directory for the evaluator-side reader (agent-effectiveness adoption,
  Revision C), and its configuration states the retention window and the fields that reader may extract.
* ``aew`` (the headless Lead): built by generalizing the M3 driver, which still runs the M3 experiment as it was.
  Until then the runner refuses an ``aew`` cell before anything is registered, so nothing is counted that never ran.

An arm's configuration is checked against its case before the attempt is registered (:meth:`Arm.check`), so a
malformed configuration is a refusal, never a counted ``invalid_measurement`` that spends a retry.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from aew_eval import fixture
from aew_eval.schemas import Invalid

HEADLESS = Path(__file__).resolve().parents[1] / "m3" / "dogfood" / "headless.py"
MODEL_REF = re.compile(r"^(?P<provider>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<model>[A-Za-z0-9][A-Za-z0-9._/-]*)"
                       r"(?:#(?P<effort>[A-Za-z0-9._-]+))?$")
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SECRET_MIN_CHARS = 8  # shorter is a placeholder, not a secret worth scanning retained state for


@dataclass
class ArmResult:
    """What an arm observed. The runner adds the fixture's facts and the validity verdict."""

    outcome: dict[str, Any] = field(default_factory=dict)
    observed_profiles: list[dict[str, Any]] = field(default_factory=list)
    harness: dict[str, Any] = field(default_factory=dict)
    aew_facts: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    invalid: str | None = None  # a reason code when the arm observed that its own measurement cannot count


class Arm(Protocol):
    kind: str

    def check(self, config: dict[str, Any], snap: fixture.Snapshot) -> None: ...

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> ArmResult:
        ...


class ScriptedArm:
    """Applies its configuration's ``steps`` in order: ``{"write": PATH, "content": TEXT}`` or ``{"delete": PATH}``.
    Paths are relative, ``/``-separated and stay inside the repository, never in ``.git``. No model, no provider,
    no network."""

    kind = "scripted"

    def check(self, config: dict[str, Any], snap: fixture.Snapshot) -> None:
        if config.get("seeded"):
            fixture.starting_files(snap, seeded=True)  # refuses a case without a seeded tree
        steps = config.get("steps", [])
        if not isinstance(steps, list):
            raise Invalid("a scripted arm's steps are a list")
        for n, step in enumerate(steps, 1):
            if not isinstance(step, dict) or len({"write", "delete"} & step.keys()) != 1:
                raise Invalid(f"scripted step {n} is one of write or delete: {step!r}")
            rel = step.get("write", step.get("delete"))
            if not isinstance(rel, str):
                raise Invalid(f"scripted step {n} names no path: {step!r}")
            fixture.safe_relative(rel, f"scripted step {n}")
            if "write" in step and not isinstance(step.get("content", ""), str):
                raise Invalid(f"scripted step {n}: content is text")

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> ArmResult:
        root = repo.resolve()
        steps = config.get("steps") or []
        for n, step in enumerate(steps, 1):
            rel = fixture.safe_relative(step.get("write") or step.get("delete"), f"scripted step {n}")
            target = root / rel
            if root not in target.resolve().parents:  # a link made by an earlier step is never followed out
                raise Invalid(f"scripted step {n} leaves the repository: {rel}")
            if "write" in step:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(step.get("content", "")), encoding="utf-8", newline="\n")
            else:
                target.unlink()
        return ArmResult(outcome={"steps": len(steps)}, harness={"name": "scripted"})


def model_ref(ref: Any) -> dict[str, str]:
    """``provider/model[#effort]`` as the profile the harness pins: ``{provider, model[, effort]}``."""
    found = MODEL_REF.match(ref) if isinstance(ref, str) else None
    if found is None:
        raise Invalid(f"a model is provider/model[#effort], not {ref!r}")
    return {k: v for k, v in found.groupdict().items() if v}


def _headless() -> ModuleType:
    """The M3 driver's headless OpenCode session, loaded from its file (``eval/m3/dogfood`` is not a package)."""
    spec = importlib.util.spec_from_file_location("aew_eval_m3_headless", HEADLESS)
    if spec is None or spec.loader is None:
        raise Invalid(f"the headless OpenCode session is missing: {HEADLESS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def files_holding(root: Path, secrets: list[bytes]) -> list[str]:
    """Every regular file under ``root`` (relative, ``/``-separated) that holds one of ``secrets``."""
    hits = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if any(s in data for s in secrets):
            hits.append(path.relative_to(root).as_posix())
    return hits


def retained_until(days: int, now: datetime | None = None) -> str:
    """The last day a run's session database may be kept (UTC), from the preregistered retention window."""
    return ((now or datetime.now(UTC)) + timedelta(days=days)).strftime("%Y-%m-%d")


def raw_invalid(*, leaked: list[str], steps: int | None) -> str | None:
    """Why a raw run's measurement cannot count, if it cannot: a secret in its retained state, or no model step at all
    (the provider failed before the model acted: an outage, a rate limit, a rejected key), which says nothing about
    the model."""
    if leaked:
        return "PROVIDER_KEY_RETAINED"
    if not steps:
        return "NO_MODEL_STEP"
    return None


class RawArm:
    """The harness alone: OpenCode's own ``build`` agent with the pinned model and the case's task as its one message.

    Its configuration is frozen in the preregistration, so every key is material::

        role: worker                       # the role in ``profiles.roles`` whose model this arm runs
        model: provider/model[#effort]     # that role's pinned model (the runner checks they agree)
        steps: 80                          # the agent's step limit
        cap_usd: 1.0                       # the turn is stopped once OpenCode's reported cost passes this
        provider_env: [NAME, ...]          # provider variables only the harness server gets ([] for a free model)
        session_db:                        # the harness session database, kept for the evaluator-side reader
          retain: true
          retention_days: 180              # no default: the experiment states it (adoption record, Revision C)
          fields: [...]                    # what that reader may extract, and nothing else

    The run's harness state, its session database included, stays in ``<scratch>/harness``; the result names the
    database, its hash and the last day it may be kept. A provider variable's value found in any file the run left
    makes the measurement invalid (``PROVIDER_KEY_RETAINED``): retained state must never hold a secret. So does a run
    in which the model never took a step (``NO_MODEL_STEP``): the provider failed, and the model was not measured.
    """

    kind = "raw"
    agent = "build"

    def check(self, config: dict[str, Any], snap: fixture.Snapshot) -> None:
        if not isinstance(config, dict):
            raise Invalid("a raw arm's configuration is a mapping")
        if not isinstance(snap.case.manifest.get("task"), str):
            raise Invalid(f"case {snap.case.id} has no task: a raw arm sends the case's task as its first message")
        if not isinstance(config.get("role"), str) or not config["role"]:
            raise Invalid("a raw arm names the role whose pinned model it runs (role)")
        model_ref(config.get("model"))
        for key in ("steps", "cap_usd"):
            value = config.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise Invalid(f"a raw arm's {key} is a positive number, not {value!r}")
        if not isinstance(config["steps"], int):
            raise Invalid("a raw arm's steps is a whole number")
        names = config.get("provider_env")
        if not isinstance(names, list) or not all(isinstance(n, str) and ENV_NAME.match(n) for n in names):
            raise Invalid("a raw arm's provider_env is a list of environment variable names ([] for a free model)")
        own = [n for n in names if n.startswith("AEW_")]
        if own:  # the adapter never passes AEW's own variables to a harness, so the provider would never get it
            raise Invalid(f"{', '.join(own)}: AEW's own variables never reach a harness; name the provider's variable")
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            raise Invalid(f"{', '.join(missing)} is not set: the raw arm's provider needs it in the runner's "
                          "environment (only the harness server receives it)")
        db = config.get("session_db")
        if not isinstance(db, dict) or db.get("retain") is not True:
            raise Invalid("a raw arm keeps its harness session database (session_db.retain: true)")
        days = db.get("retention_days")
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise Invalid("session_db.retention_days is a positive whole number: the retention window has no default")
        fields = db.get("fields")
        if not isinstance(fields, list) or not fields or not all(isinstance(f, str) and f for f in fields):
            raise Invalid("session_db.fields names what the evaluator-side reader may extract (a non-empty list)")

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> ArmResult:
        if not task:
            raise Invalid("a raw arm needs the case's task")
        from aew.harness.opencode import adapter as oc  # the binary the server runs: its identity is recorded

        headless = _headless()
        profile = model_ref(config["model"])
        names = list(config["provider_env"])
        secrets = [os.environ[n].encode() for n in names if len(os.environ.get(n) or "") >= SECRET_MIN_CHARS]
        scratch = repo.parent
        session = headless.HeadlessSession(scratch / "harness")
        cap = float(config["cap_usd"])

        def over_cap() -> str | None:
            return "cost_cap" if float(session.live_usage().get("cost") or 0) > cap else None

        ended = "not_started"
        try:
            session.open(directory=repo, profile=profile, agent=self.agent,
                         config=headless.raw_config(profile, int(config["steps"])),
                         env=headless.shell_env(os.environ), provider_env=names, title="raw OpenCode (evaluation)")
            session.say(task)
            ended = session.wait_turn(time.monotonic() + deadline_s, over_cap)
        finally:
            summary = session.close()
        state = Path(getattr(session, "state_dir", scratch / "harness" / "harness"))
        db = state / "xdg-data" / "opencode" / "opencode.db"
        retain = config["session_db"]
        leaked = files_holding(scratch, secrets) if secrets else []
        usage = summary.get("usage") or {}
        observed = [{"role": config["role"], "provider": e.get("provider"), "model": e.get("model"),
                     "effort": e.get("effort"), **({"effort_unreported": True} if e.get("effort_unreported") else {})}
                    for e in summary.get("effective") or []]
        return ArmResult(
            outcome={
                "harness_outcome": ended, "steps": summary.get("steps"), "turns": len(summary.get("turns") or []),
                "tools_called": summary.get("tools_called"), "last_detail": summary.get("last_detail"),
                "permission_rejected": [r.get("action") for r in summary.get("permission_rejected") or []],
                "forms_cancelled": len(summary.get("forms_cancelled") or []),
                "foreign_sessions": summary.get("foreign_sessions") or [],
                "session_db": {"path": db.relative_to(scratch).as_posix() if db.is_file() else None,
                               "sha256": _sha256_file(db) if db.is_file() else None,
                               "retain_until": retained_until(int(retain["retention_days"])),
                               "fields": list(retain["fields"])},
                "provider_key_files": leaked},
            observed_profiles=observed,
            harness={"name": "opencode", "agent": self.agent, "version": summary.get("version"),
                     "artifact_sha256": _sha256_file(Path(oc.binary_command()[-1])), "catalog": summary.get("catalog")},
            cost={"provider_reported_usd": usage.get("cost"), "tokens": usage.get("tokens"),
                  "usage_record": summary.get("usage_record")},
            invalid=raw_invalid(leaked=leaked, steps=summary.get("steps")))


ARMS: dict[str, Arm] = {"scripted": ScriptedArm(), "raw": RawArm()}


def arm_for(kind: str) -> Arm:
    """The arm for ``kind``, or a refusal naming what runs it today."""
    if kind not in ARMS:
        raise Invalid(f"arm kind {kind!r} is not built in the shared runner yet: the M3 driver "
                      "(eval/m3/dogfood/dogfood.py) runs it until it is generalized (design §8, step 2)")
    return ARMS[kind]
