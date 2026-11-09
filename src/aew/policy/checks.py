"""Project-defined deterministic check runner (WC §11.1-11.2, §16.14).

Checks are the cheapest reliable evidence producers: build, focused tests,
linters. The command comes from project policy, never from the agent. The
placeholder ``{python}`` expands to the running interpreter.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aew.engine import faults
from aew.errors import ContainmentUnavailable, GateUnsatisfied, NotFound

BUILTIN = {"guardrails"}
DEFAULT_TIMEOUT_S = 900

# Display budgets, not execution/evidence limits: at most 80 lines of 1,000 characters each. The full log and its
# evidence seal are untouched. Keep the source names in the result so callers can explain the cut without guessing.
FAILURE_OUTPUT_MAX_LINES = 80
FAILURE_OUTPUT_MAX_LINE_CHARS = 1000
_FAILURE_LINE = re.compile(
    r"\b(?:fail(?:ed|ure|ures)?|errors?|traceback|\w*exception|assert(?:ion\w*)?|timeout|violations)\b|^E\s+", re.I)


def failure_output(log: str) -> dict[str, Any]:
    """A bounded, credential-scrubbed diagnostic view, with original 1-based line numbers and exact omitted counts.

    Prefer diagnostic anchors anywhere in the log, then their two-line context, then the tail. This is a heuristic,
    not a parser for every test runner: without recognisable anchors it is a tail, explicitly only an excerpt. If
    anchors themselves exceed the budget, earlier anchors win. Scrub whole lines before truncating, never a prefix
    of a credential. The saved log and sealed evidence never pass through this display helper.
    """
    from aew.harness.contract import redact

    lines = log.splitlines()
    anchors = [i for i, line in enumerate(lines) if _FAILURE_LINE.search(line)]
    selected: set[int] = set()
    for indices in (anchors, [j for i in anchors for j in range(max(0, i - 2), min(len(lines), i + 3))],
                    range(len(lines) - 1, -1, -1)):
        for i in indices:
            if len(selected) == FAILURE_OUTPUT_MAX_LINES:
                break
            selected.add(i)
    out = []
    truncated = 0
    for i in sorted(selected):
        text = redact(lines[i])
        cut = len(text) > FAILURE_OUTPUT_MAX_LINE_CHARS
        truncated += int(cut)
        out.append({"line": i + 1, "text": text[:FAILURE_OUTPUT_MAX_LINE_CHARS], "truncated": cut})
    return {"lines": out, "total_lines": len(lines), "omitted_lines": len(lines) - len(out),
            "truncated_lines": truncated,
            "limits": {"lines": FAILURE_OUTPUT_MAX_LINES, "characters_per_line": FAILURE_OUTPUT_MAX_LINE_CHARS,
                       "source": "aew.policy.checks.FAILURE_OUTPUT_MAX_LINES / FAILURE_OUTPUT_MAX_LINE_CHARS"}}


def definition_digest(cfg: dict[str, Any], *, guardrails: dict[str, Any] | None = None) -> str:
    """What a result of this check proves: the definition that ran (independent audit I1). For a configured check,
    its command, working directory and timeout (a description is not part of it); for the builtin guardrails check,
    the guardrails policy it evaluated."""
    if cfg.get("builtin"):
        basis: dict[str, Any] = {"builtin": "guardrails", "policy": guardrails}
    else:
        basis = {"command": cfg.get("command"), "cwd": cfg.get("cwd", "."),
                 "timeout_s": cfg.get("timeout_s", DEFAULT_TIMEOUT_S)}
        if cfg.get("network"):  # F28 §3.8; absent, the digest is what it was before checks could ask for a network
            basis["network"] = cfg["network"]
    return hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def current_definitions(checks_policy: dict[str, Any], guardrails: dict[str, Any]) -> dict[str, str]:
    """Each check id's definition digest under the policy now in force. An unconfigured check has none."""
    out = {"guardrails": definition_digest({"builtin": True}, guardrails=guardrails)}
    for check_id, cfg in (checks_policy.get("checks") or {}).items():
        if cfg.get("configured") and cfg.get("command"):
            out[check_id] = definition_digest(cfg)
    return out


def proves_current_definition(evidence: dict[str, Any], definitions: dict[str, str]) -> bool:
    """A check result counts only for the check as it is defined now (decision (a), independent audit I1). A result
    recorded without a definition, or for a check no longer configured, proves nothing about the current one."""
    check = evidence.get("check") or {}
    current = definitions.get(str(check.get("check_id")))
    return current is not None and check.get("definition_sha256") == current


def resolve(checks_policy: dict[str, Any], check_id: str) -> dict[str, Any]:
    if check_id in BUILTIN:
        return {"builtin": True}
    cfg = checks_policy["checks"].get(check_id)
    if cfg is None:
        raise NotFound(f"no check {check_id!r} in policy/checks.yaml")
    if not cfg.get("configured") or not cfg.get("command"):
        raise GateUnsatisfied(
            f"check {check_id!r} is not configured; configure policy/checks.yaml rather than guessing a command")
    return cfg


def allowlist_env(layout: Any) -> dict[str, str]:
    """A check's environment where nothing hands it one: operating-system basics and the sandbox's own settings, never
    a credential or anything else the caller's shell held (the check runs code an agent wrote)."""
    from aew.harness.agentenv import POSIX_KEEP, WINDOWS_KEEP

    keep = WINDOWS_KEEP if sys.platform == "win32" else POSIX_KEEP
    env = {k: v for k, v in os.environ.items()
           if k.upper() in keep or (sys.platform != "win32" and k.startswith("LC_"))}
    env["PATH"] = os.environ.get("PATH") or os.environ.get("Path") or ""
    env["PYTHONUTF8"] = "1"
    env.update(getattr(layout, "env", None) or {})
    return env


def run(cfg: dict[str, Any], workspace: Path, *, policy: dict[str, Any] | None, env: dict[str, str] | None = None,
        layout: Any = None, trees: Any = None) -> dict[str, Any]:
    """Run a check in its own process tree. Every process it started has ended when this returns, so the caller's
    after-snapshot describes everything the check did (independent audit I2). With ``layout`` (a contained run's
    sandbox) the tree starts the check inside it (M4-B), with no network unless the check's ``network: shared`` and the
    run's own network allow the host's (F28 §3.8; ``containment.for_check``); the result records which. ``trees`` (a
    run's supervisor) holds the check's tree while it runs, so the run ending ends the check, and gathers what each
    check's tree left running (``CheckTrees.left``).

    ``policy`` is the execution policy the check runs under, which every caller passes. Under its ``required``, a check
    with no layout is refused before anything starts, whatever started it (DV-4's backstop): the tree requires one.
    Such a refusal, like any containment failure at the spawn (bubblewrap's argument limit, addendum 9), is raised as
    the ``ContainmentUnavailable`` it is, never reported as a check that could not start (E114)."""
    from aew.harness import containment
    from aew.harness.containment.layout import for_check
    from aew.harness.procs import ProcessTree

    command = [part.replace("{python}", sys.executable) for part in cfg["command"]]
    cwd = (workspace / cfg.get("cwd", ".")).resolve()
    timeout = cfg.get("timeout_s", DEFAULT_TIMEOUT_S)
    started = time.monotonic()
    layout = for_check(layout, cfg.get("network")) if layout is not None else None
    required = containment.mode(policy) == containment.REQUIRED
    if required and layout is None:
        raise ContainmentUnavailable(
            f"the check `{' '.join(command)[:80]}` would run with no sandbox, and the execution policy requires "
            f"containment (containment.mode: required): it is refused before anything starts. Run it contained, or "
            f"{containment.ALLOW_WEAKER_REMEDY}", reason="check_uncontained")
    tree = ProcessTree(layout=layout, require_layout=required)  # and the tree itself starts nothing without one
    if trees is not None:
        trees.add(tree)  # a run's CheckTrees: killed on arrival if the run has already ended
    faults.pause("checks.before_spawn")  # tests: the run ends between registration and start (M4-B review)
    exit_code: int | None = None
    outcome, spawn_errno = "ran", None
    try:
        try:
            proc = tree.spawn(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              stdin=subprocess.DEVNULL, env=env, text=True)
        except OSError as exc:
            outcome, spawn_errno = "spawn_failed", exc.errno
            log = f"$ {' '.join(command)}\nfailed to start: {exc}"
        else:
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                exit_code = proc.returncode
                log = f"$ {' '.join(command)}\n(cwd {cwd}){_network_line(layout)}\n\n--- stdout ---\n{stdout}\n" \
                      f"--- stderr ---\n{stderr}"
            except subprocess.TimeoutExpired:
                outcome = "timeout"
                tree.kill()
                stdout, stderr = proc.communicate()
                log = f"$ {' '.join(command)}\nTIMEOUT after {timeout}s\n{stdout or ''}\n{stderr or ''}"
    finally:
        left = tree.close()
        if trees is not None:
            if left:  # the register of weaker contexts ends a run's entry only once these are proven ended
                trees.left.extend(tree.survivors(0.0))
            trees.discard(tree)
    if left and exit_code is not None:
        log += "\n--- processes the check left running were ended when it returned ---\n"
    # ``outcome`` tells a check that could not start (``spawn_failed``, with its errno) or ran out of time (``timeout``)
    # from one that ran: integration validation (M4-D5) treats the first as infrastructure, the second as inconclusive.
    return {"exit_code": exit_code, "duration_s": round(time.monotonic() - started, 3), "log": log,
            "command": command, "outcome": outcome, "spawn_errno": spawn_errno,
            "network": layout.network if layout is not None else None}


def _network_line(layout: Any) -> str:
    """The check's network, in its log, so a check that failed for want of one says so (F28 §3.8)."""
    if layout is None or not layout.private_network:
        return ""
    return ("\n(network: none; a check that needs the network declares `network: shared`, which it gets when the run's "
            "network mode is shared)")
