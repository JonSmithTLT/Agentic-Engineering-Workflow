"""The raw arm: the harness alone (evaluation component design v0.2, §2 and decision 2; agent-effectiveness adoption,
delta D3).

OpenCode's own ``build`` agent, the pinned model, the case's ``task`` as its only message, nobody answering: the M3
raw mode (``eval/m3/dogfood/dogfood.py --mode raw``), generalized. It drives OpenCode through the M3 driver's headless
session (``eval/m3/dogfood/headless.py``, reused rather than copied): a private server and private state, the
provider variables only in the server's environment, a curated shell environment, every permission request or form
rejected.

What the frozen configuration pins, and what a run that departs from it is:

* **the harness**: name, version and the binary's sha256 for the host platform. An unpinned or different binary is
  refused before the attempt is registered; a server reporting another version makes the run ``HARNESS_MISMATCH``;
* **the profile**: the model and its effort (the role's pinned ``provider/model#effort``), the profile record's id,
  its effective profile and its qualification state at preregistration (adoption record §9);
* **containment** (``contain: true``): Linux only, the whole OpenCode process tree in a bubblewrap layout whose
  writable roots are the run's work tree and harness state, with every other entry of the home directory, every other
  run, the ledger and anything beside the lane's run state hidden (an empty tmpfs). The layout passes AEW's launch
  self-test and a confidentiality probe (each hidden path is empty from inside) before OpenCode starts;
* **the session database**: kept with the run for the evaluator-side reader (Revision C), under ``retention_days``
  and the structured field allowlist (``{field, transform}``, transform ``none``, ``prefix_300`` or ``sha256``).
  :mod:`aew_eval.retention` enforces the window.

A run is counted and not valid (``ArmResult.invalid``) when it cannot measure the model: ``PROVIDER_KEY_RETAINED`` (a
provider value in any retained file; those files are deleted at once and the deletion recorded),
``HARNESS_MISMATCH``, ``CONTAINMENT_FAILED``, ``ARM_ERROR`` (the session failed after it started; its database,
leak scan and cost are recorded all the same), ``NO_MODEL_STEP`` (no assistant step without a provider error: a
rejected key, a rate limit or an outage before the model acted) and ``PROVIDER_ERROR_ENDED_TURN`` (a provider error
ended the turn after some steps). A valid run that was cut short (the turn's deadline or cost cap, the step limit)
says so in ``outcome.truncated``, so an analysis that needs a finished run can leave it out.

A run's cost is OpenCode's reported cost; when it is unknown the run is charged its ``cap_usd`` (``cost.charged_usd``),
so a budget never undercounts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from aew_eval import fixture
from aew_eval.arms import ArmResult, model_ref
from aew_eval.schemas import Invalid

HEADLESS = Path(__file__).resolve().parents[1] / "m3" / "dogfood" / "headless.py"
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SECRET_MIN_CHARS = 8  # shorter is a placeholder, not a secret worth scanning retained state for
TRANSFORMS = ("none", "prefix_300", "sha256")
EFFECTIVE_KEYS = ("context.orientation", "tools.presentation")


def host_platform() -> str:
    """The key a harness pin uses for this host: ``<sys.platform>-<arch>`` (``win32-x64``, ``linux-x64``)."""
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(machine, machine)
    return f"{sys.platform}-{arch}"


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


def harness_binary() -> Path:
    from aew.harness.opencode import adapter as oc

    return Path(oc.binary_command()[-1])


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


def purge_files(root: Path, rels: list[str]) -> list[str]:
    """Delete the files ``rels`` under ``root`` (a secret must not be retained); the ones actually deleted."""
    gone = []
    for rel in rels:
        try:
            (root / rel).unlink()
            gone.append(rel)
        except FileNotFoundError:
            gone.append(rel)
        except OSError:
            continue
    return gone


def retained_until(days: int, now: datetime | None = None) -> str:
    """The last day a run's session database may be kept (UTC), from the preregistered retention window."""
    return ((now or datetime.now(UTC)) + timedelta(days=days)).strftime("%Y-%m-%d")


def step_facts(assistant: list[dict[str, Any]]) -> dict[str, Any]:
    """What the session's assistant messages say about the model: a message that carries a provider error (a
    rejected key, a rate limit, an outage) is not a model step."""
    errored = [m for m in assistant if m.get("error")]
    last = assistant[-1] if assistant else None
    return {"assistant_messages": len(assistant), "model_steps": len(assistant) - len(errored),
            "errored_steps": len(errored), "errors": [m["error"] for m in errored][:5],
            "ended_by_provider_error": bool(last and last.get("error"))}


def truncation(*, ended: str, facts: dict[str, Any], steps_limit: int) -> list[str]:
    """Why a valid run did not finish on its own, if it did not: the turn's deadline or cost cap, the step limit, a
    provider error at the end. Empty for a run whose turn ended by itself."""
    why = []
    if ended != "ended":
        why.append(f"turn:{ended}")
    if facts["assistant_messages"] >= steps_limit:
        why.append("step_limit")
    if facts["ended_by_provider_error"]:
        why.append("provider_error")
    return why


def raw_invalid(*, leaked: list[str], facts: dict[str, Any], arm_error: str | None = None,
                harness_mismatch: bool = False, containment_failed: bool = False) -> str | None:
    """Why a raw run's measurement cannot count, if it cannot (the module's docstring lists the reasons)."""
    if leaked:
        return "PROVIDER_KEY_RETAINED"
    if containment_failed:
        return "CONTAINMENT_FAILED"
    if harness_mismatch:
        return "HARNESS_MISMATCH"
    if arm_error:
        return "ARM_ERROR"
    if not facts["model_steps"]:
        return "NO_MODEL_STEP"
    if facts["ended_by_provider_error"]:
        return "PROVIDER_ERROR_ENDED_TURN"
    return None


def charged(reported: Any, cap: float) -> float:
    """What a run is charged against a budget: its reported cost, or its cap when the cost is unknown."""
    try:
        return float(reported) if reported is not None else float(cap)
    except (TypeError, ValueError):
        return float(cap)


# ---------------------------------------------------------------------------------------------- containment


def hidden_around(home: Path, keep: list[Path]) -> tuple[list[str], list[str]]:
    """Every entry beside the paths to ``keep``, from the home directory down: what a contained run must not see.

    Each kept path's ancestors under ``home`` are walked; at each level every sibling that is not itself on a kept
    path's chain is hidden (a directory by an empty tmpfs, a file by an empty file). Nothing inside a kept path is
    hidden here. Paths outside ``home`` are left to the layout's read-only host root."""
    home = home.resolve()
    keep = [p.resolve() for p in keep]
    keep = [p for p in keep if p != home and p not in home.parents]  # keeping all of home would hide nothing
    chain: set[Path] = set()
    for p in keep:
        if p == home or home in p.parents:
            chain.add(p)
            chain.update(a for a in p.parents if a == home or home in a.parents)
    # the home directory itself is always scanned: with nothing kept under it, every entry of it is hidden
    scan = sorted({home, *(a for a in chain if any(a in p.parents for p in keep) and a not in keep)})
    dirs: list[str] = []
    files: list[str] = []
    for d in scan:
        try:
            children = sorted(d.iterdir())
        except OSError:
            continue
        for child in children:
            real = child.resolve()
            if real in chain or child in chain:
                continue
            if child.is_symlink():
                continue  # its target is hidden or kept on its own terms
            if child.is_dir():
                dirs.append(str(real))
            elif child.is_file():
                files.append(str(real))
    return sorted(set(dirs)), sorted(set(files))


_CONFIDENTIALITY = r"""
import json, os, sys
spec = json.loads(sys.argv[1])
seen = []
for d in spec["dirs"]:
    try:
        if os.listdir(d):
            seen.append(d)
    except OSError:
        pass
for d, allowed in spec["runs"].items():
    try:
        if set(os.listdir(d)) - set(allowed):
            seen.append(d)
    except OSError:
        pass
for f in spec["files"]:
    try:
        with open(f, "rb") as fh:
            if fh.read(1):
                seen.append(f)
    except OSError:
        pass
print(json.dumps({"visible": seen}))
"""


def contained_layout(repo: Path, scratch: Path, *, binary: Path) -> Any:
    """The bubblewrap layout of one raw run (Linux): writable the work tree and the run's harness state, hidden
    every other run, everything beside the lane's run state and every home entry the run does not need."""
    from aew.harness.containment import layout as L

    bwrap = L.find_bwrap()
    if bwrap is None:
        raise Invalid("a contained raw arm needs bubblewrap (bwrap) on this host")
    state = scratch / "harness"
    state.mkdir(parents=True, exist_ok=True)
    home = Path(os.path.expanduser("~"))
    keep = [scratch, binary.parent, Path(sys.prefix), Path(sys.base_prefix),
            *(Path(p) for p in sys.path if p and os.path.isdir(p))]
    hide_dirs, hide_files = hidden_around(home, keep)
    secret_dirs, secret_files = L._masks(str(home), [])  # noqa: SLF001 (the same secret masks as every AEW run)
    mask = scratch.parent / f".{scratch.name}.aew-mask"  # outside the writable roots, and itself hidden inside
    if not mask.exists():
        mask.write_bytes(b"")
    # the interpreter and the harness binary's directory stay visible wherever they live (even under /tmp, which the
    # sandbox replaces with its own)
    readonly = sorted({os.path.realpath(p) for p in (sys.prefix, sys.base_prefix, str(binary.parent))
                       if p and os.path.isdir(p)})
    dirs = outermost({*hide_dirs, *secret_dirs})
    files = [f for f in sorted({*hide_files, *secret_files}) if not any(_under(f, d) for d in dirs)]
    return L.Layout(role="eval-raw", access="write", bwrap=bwrap,
                    writable=(os.path.realpath(repo), os.path.realpath(state)), readonly=tuple(readonly),
                    hide_runs=(os.path.realpath(scratch.parent),), hide_dirs=tuple(dirs), hide_files=tuple(files),
                    mask_file=str(mask), env={"TMPDIR": L.SANDBOX_TMP})


def _under(path: str, root: str) -> bool:
    return path != root and path.startswith(root.rstrip(os.sep) + os.sep)


def outermost(paths: set[str]) -> list[str]:
    """The hidden directories without those inside another: a mask nested in a hidden directory would leave its
    mount point behind as an (empty) entry of the hidden directory."""
    return sorted(p for p in paths if not any(_under(p, q) for q in paths))


def verify_layout(layout: Any, scratch: Path) -> dict[str, Any]:
    """AEW's launch self-test (writes stay in the writable roots) and a confidentiality probe (every hidden path is
    empty from inside), before any harness process starts."""
    from aew.harness.containment import bwrap_argv
    from aew.harness.containment.probe import self_test

    integrity = self_test(layout, sentinel_dir=scratch.parent, sibling_dir=scratch.parent)
    spec = {"dirs": list(layout.hide_dirs), "files": list(layout.hide_files),
            "runs": {r: [scratch.name] for r in layout.hide_runs}}  # only this run's own directory shows there
    try:
        done = subprocess.run(bwrap_argv(layout, [sys.executable, "-I", "-c", _CONFIDENTIALITY, json.dumps(spec)]),
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                              env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"})
        visible = json.loads(done.stdout.strip().splitlines()[-1])["visible"] if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, KeyError):
        visible = None
    ok = bool(integrity.get("ok")) and visible == []
    reason = integrity.get("reason") or (None if visible == [] else
                                         f"hidden paths visible from inside: {visible}" if visible else
                                         "the confidentiality probe did not run")
    return {"ok": ok, "reason": reason, "hidden_dirs": len(layout.hide_dirs), "hidden_files": len(layout.hide_files)}


# ---------------------------------------------------------------------------------------------- the arm


class RawArm:
    """The harness alone (see the module docstring). Its configuration, frozen in the preregistration::

        role: worker
        model: provider/model#effort         # the role's pinned model, with its effort (the runner checks)
        profile: {id, effective_profile: {context.orientation, tools.presentation}, qualification_state}
        harness: {name: opencode, version: 2.0.18, artifact_sha256: {<platform>: <sha256>, ...}}
        contain: true                        # Linux bubblewrap; refused elsewhere
        steps: 80
        cap_usd: 0.75
        provider_env: [NAME, ...]            # names only; [] for a free model
        session_db: {retain: true, retention_days: 180, fields: [{field, transform}, ...]}
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
        if not isinstance(config.get("contain"), bool):
            raise Invalid("a raw arm says whether it runs contained (contain: true | false)")
        if config["contain"] and not sys.platform.startswith("linux"):
            raise Invalid("a contained raw arm runs only on Linux with bubblewrap; this host cannot contain it")
        self._check_profile(config.get("profile"))
        self._check_harness(config.get("harness"))
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
        self._check_session_db(config.get("session_db"))

    @staticmethod
    def _check_profile(profile: Any) -> None:
        if not isinstance(profile, dict) or not isinstance(profile.get("id"), str) or not profile["id"]:
            raise Invalid("a raw arm pins its profile record (profile.id)")
        effective = profile.get("effective_profile")
        if not isinstance(effective, dict) or set(effective) != set(EFFECTIVE_KEYS):
            raise Invalid(f"profile.effective_profile names exactly {', '.join(EFFECTIVE_KEYS)} (null for raw)")
        if not isinstance(profile.get("qualification_state"), str):
            raise Invalid("profile.qualification_state is the profile's state at preregistration")

    @staticmethod
    def _check_harness(harness: Any) -> None:
        if not isinstance(harness, dict) or harness.get("name") != "opencode" or not harness.get("version"):
            raise Invalid("a raw arm pins its harness: {name: opencode, version, artifact_sha256}")
        pins = harness.get("artifact_sha256")
        if not isinstance(pins, dict) or not pins or not all(isinstance(v, str) and SHA256.match(v)
                                                            for v in pins.values()):
            raise Invalid("harness.artifact_sha256 maps each host platform to the pinned binary's sha256")
        here = host_platform()
        if here not in pins:
            raise Invalid(f"no pinned harness binary for this host ({here}); pinned: {sorted(pins)}")
        try:
            binary = harness_binary()
        except Exception as exc:  # noqa: BLE001 (no binary at all is a refusal like any other)
            raise Invalid(f"the pinned harness is not installed here: {exc}") from None
        if _sha256_file(binary) != pins[here]:
            raise Invalid(f"the harness binary {binary} is not the pinned one for {here} (sha256 differs)")

    @staticmethod
    def _check_session_db(db: Any) -> None:
        if not isinstance(db, dict) or db.get("retain") is not True:
            raise Invalid("a raw arm keeps its harness session database (session_db.retain: true)")
        days = db.get("retention_days")
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise Invalid("session_db.retention_days is a positive whole number: the retention window has no default")
        fields = db.get("fields")
        if not isinstance(fields, list) or not fields:
            raise Invalid("session_db.fields lists what the evaluator-side reader may extract (non-empty)")
        for f in fields:
            if not isinstance(f, dict) or set(f) != {"field", "transform"} or not isinstance(f["field"], str) \
                    or not f["field"] or f["transform"] not in TRANSFORMS:
                raise Invalid(f"a session_db field is {{field, transform}} with transform one of {TRANSFORMS}: {f!r}")

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> ArmResult:
        if not task:
            raise Invalid("a raw arm needs the case's task")
        from aew.harness import procs

        headless = _headless()
        profile = model_ref(config["model"])
        names = list(config["provider_env"])
        secrets = [os.environ[n].encode() for n in names if len(os.environ.get(n) or "") >= SECRET_MIN_CHARS]
        scratch = repo.parent
        binary = harness_binary()
        containment: dict[str, Any] = {"contained": False}
        session = headless.HeadlessSession(scratch / "harness")
        cap = float(config["cap_usd"])

        def over_cap() -> str | None:
            return "cost_cap" if float(session.live_usage().get("cost") or 0) > cap else None

        ended, arm_error = "not_started", None
        try:
            if config["contain"]:
                layout = contained_layout(repo, scratch, binary=binary)
                containment = {"contained": True, "mechanism": "bubblewrap", **verify_layout(layout, scratch)}
                if not containment["ok"]:
                    raise Invalid(f"containment failed: {containment['reason']}")
                session.tree = procs.ProcessTree(layout=layout)
            session.open(directory=repo, profile=profile, agent=self.agent,
                         config=headless.raw_config(profile, int(config["steps"])),
                         env=headless.shell_env(os.environ), provider_env=names, title="raw OpenCode (evaluation)")
            session.say(task)
            ended = session.wait_turn(time.monotonic() + deadline_s, over_cap)
        except Exception as exc:  # noqa: BLE001 (the run is counted either way; its facts are still collected)
            arm_error = f"{type(exc).__name__}: {exc}"[-600:]
        try:
            summary = session.close()
        except Exception as exc:  # noqa: BLE001
            summary = {}
            arm_error = arm_error or f"close: {type(exc).__name__}: {exc}"[-600:]
        snapshot = getattr(session, "snapshot", None) or {}
        facts = step_facts(list(snapshot.get("assistant") or []))
        state = scratch / "harness"
        db = Path(getattr(session, "state_dir", state / "harness")) / "xdg-data" / "opencode" / "opencode.db"
        leaked = files_holding(scratch, secrets) if secrets else []
        purged = purge_files(scratch, leaked) if leaked else []
        usage = summary.get("usage") or {}
        reported = usage.get("cost")
        version = summary.get("version")
        mismatch = version is not None and str(version) != str(config["harness"]["version"])
        observed = [{"role": config["role"], "provider": e.get("provider"), "model": e.get("model"),
                     "effort": e.get("effort"), **({"effort_unreported": True} if e.get("effort_unreported") else {})}
                    for e in summary.get("effective") or []]
        why = truncation(ended=ended, facts=facts, steps_limit=int(config["steps"]))
        return ArmResult(
            outcome={
                "harness_outcome": ended, **facts, "steps": summary.get("steps"),
                "truncated": bool(why), "truncated_why": why, "arm_error": arm_error,
                "turns": len(summary.get("turns") or []), "tools_called": summary.get("tools_called"),
                "last_detail": summary.get("last_detail"),
                "permission_rejected": [r.get("action") for r in summary.get("permission_rejected") or []],
                "forms_cancelled": len(summary.get("forms_cancelled") or []),
                "foreign_sessions": summary.get("foreign_sessions") or [],
                "containment": containment,
                "session_db": {"state_dir": str(state.resolve()),
                               "path": db.relative_to(scratch).as_posix() if db.is_file() else None,
                               "sha256": _sha256_file(db) if db.is_file() else None,
                               "retain_until": retained_until(int(config["session_db"]["retention_days"])),
                               "fields": list(config["session_db"]["fields"])},
                "provider_key_files": leaked, "provider_key_files_purged": purged},
            observed_profiles=observed,
            harness={"name": "opencode", "agent": self.agent, "version": version,
                     "pinned_version": config["harness"]["version"], "platform": host_platform(),
                     "artifact_sha256": _sha256_file(binary), "catalog": summary.get("catalog")},
            cost={"provider_reported_usd": reported, "charged_usd": charged(reported, cap),
                  "tokens": usage.get("tokens"), "usage_record": summary.get("usage_record")},
            invalid=raw_invalid(leaked=leaked, facts=facts, arm_error=arm_error, harness_mismatch=mismatch,
                                containment_failed=bool(config["contain"]) and not containment.get("ok")))
