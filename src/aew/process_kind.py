"""Which AEW processes may write the store (STG-05 CB-09; WIS-00 R2-2).

Every AEW entry point is in :data:`ENTRY_POINTS` with its kind:

* a **store writer** takes the engine's control lock: it reads under it (``ControlStore.read``, which may recover),
  opens transactions (``session``) and initializes projects (``create``);
* a **non-writer** reads only lock-free: ``ControlStore.read_committed``, ``configuration.read_committed``,
  ``outbox.LogView`` and ``outbox.read_transitions``. These take no lock and run no recovery, so they work on a
  read-only store. Anything that needs the lock goes through the bridge of the process that holds the credential.

An entry point declares itself once, at process start (:func:`declare`); ``ControlStore`` refuses ``read``,
``session`` and ``create`` in a non-writer before it opens the lock (:func:`require_writer`). A process that declared
nothing (library use, a test calling the engine in-process) is a store writer, as before.

The declaration is how AEW's own processes behave; it is not the boundary. A contained agent can unset the variables
it is judged by, so a sandbox never relies on it: the store is read-only there, and the control lock is outside the
agent's layout (``aew.harness.containment.layout``). This module imports nothing from the engine, so an inventory (the
work-item fact issuer's gate) can read the table without loading AEW.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

STORE_WRITER = "store_writer"
NON_WRITER = "non_writer"

# entry point -> (kind, why). Exhaustive for AEW's own processes, and a test compares it with every module that runs
# as one (`if __name__ == "__main__"`, `aew/__main__.py`, the console script): the `aew` CLI (and `python -m aew`), in
# the four roles it plays, and each `python -m` module by its dotted name. The Lead broker runs the CLI in its own
# process (`lead_broker.run_cli`, not through `main`), so it declares nothing and is a store writer, as it must be: it
# holds the Lead's credential and commits for the Lead.
ENTRY_POINTS: dict[str, tuple[str, str]] = {
    "aew": (STORE_WRITER, "the CLI the operator, the Lead and AEW's own workers (the custody worker) run: engine "
            "commands take the control lock"),
    "aew dashboard serve": (NON_WRITER, "the dashboard server, long-running and read-only: it reads the store "
                            "lock-free (dashboard.reader) and serializes its own publication with its endpoint lock, "
                            "never the control lock"),
    "aew (worker run)": (NON_WRITER, "the CLI inside a worker's harness run (AEW_AGENT_ENDPOINT set): `whoami`, "
                         "`check run` and `submit` go through the run's bridge, whose supervisor holds the "
                         "credential and the lock; nothing else in that process may take the lock"),
    "aew (contained Lead)": (NON_WRITER, "the CLI inside the contained Lead's sandbox (AEW_LEAD_CONTAINED set): its "
                             "Lead-authenticated commands go through the Lead broker, which holds the credential and "
                             "the lock, and it reads lock-free, since the sandbox holds no control lock (`.aew/local` "
                             "is masked) and `.aew` is read-only there; and the reads that broker relays to the host "
                             "for it (lead_broker.RELAYED_READS), which read lock-free there too and write nothing"),
    "aew lead mcp": (NON_WRITER, "the Lead's MCP transport: it constructs no engine and forwards every call to the "
                     "Lead broker, which holds the credential"),
    "aew.harness.supervisor": (STORE_WRITER, "a run's supervisor: holds the run's credential and commits through the "
                               "engine"),
    "aew.stg02.server": (NON_WRITER, "the STG-02 slice's producer: it reads a project's committed state lock-free "
                         "(dashboard.reader) and writes only its own state directory, never the store"),
}
AGENT_ENDPOINT_ENV = "AEW_AGENT_ENDPOINT"  # aew.harness.bridge.ENV_ENDPOINT, named here to keep this module free of AEW
# Set in the contained Lead's sandbox (``aew.harness.opencode.lead``, which takes it from here): how AEW's own CLI
# there behaves, never a boundary (see the module docstring).
LEAD_CONTAINED_ENV = "AEW_LEAD_CONTAINED"

_declared: str | None = None


def declare(entry_point: str) -> None:
    """Record this process's entry point; its kind is the table's. An unknown entry point is a programming error."""
    global _declared
    if entry_point not in ENTRY_POINTS:
        raise KeyError(f"{entry_point!r} is not an AEW entry point in aew.process_kind.ENTRY_POINTS")
    _declared = entry_point


@contextmanager
def declared_as(entry_point: str) -> Iterator[None]:
    """:func:`declare` for the extent of the block, then the previous declaration again (a CLI ``main`` called
    in-process, as tests do, must not leave its kind behind). The declaration is the process's, not the thread's:
    another thread sees it while the block runs. No caller runs ``main`` in a thread; one that did would need a
    ``contextvars.ContextVar`` here."""
    global _declared
    previous = _declared
    declare(entry_point)
    try:
        yield
    finally:
        _declared = previous


def cli_entry_point(argv: list[str], env: Mapping[str, str]) -> str:
    """Which of the CLI's entry points ``aew argv`` is, in ``env``."""
    if env.get(AGENT_ENDPOINT_ENV):
        return "aew (worker run)"
    words: list[str] = []
    contained = bool(env.get(LEAD_CONTAINED_ENV))
    value = False
    for arg in argv:
        if value:  # the directory of `-C <dir>`, the one global option that takes a value
            value = False
        elif arg == "-C":
            value = True
        elif not arg.startswith("-"):
            words.append(arg)
    named: dict[tuple[str, ...], str] = {("lead", "mcp"): "aew lead mcp", ("dashboard", "serve"): "aew dashboard serve"}
    return named.get(tuple(words[:2]), "aew (contained Lead)" if contained else "aew")


def declared() -> str | None:
    return _declared


def kind() -> str:
    return ENTRY_POINTS[_declared][0] if _declared is not None else STORE_WRITER


def require_writer(operation: str, *, writes: str | None = None) -> None:
    """Refuse ``operation`` in a non-writer process, before it starts: ``PERMISSION_DENIED``, reason
    ``non_writer_process``. Without ``writes`` the operation takes the control lock (``ControlStore.control_lock``, the
    one opener); with it, the operation's purpose is the write ``writes`` names under ``.aew``, which is a writer's
    (review of #231, m7), and the refusal says so."""
    if kind() != NON_WRITER:
        return
    from aew.errors import PermissionDenied

    what = (f"which writes {writes}, is refused before it writes anything" if writes is not None
            else "which takes the engine's control lock, is refused before the lock is opened")
    raise PermissionDenied(
        f"this process ({_declared}) reads AEW's store lock-free only, so `{operation}`, {what}. Inside a worker's "
        "run, `aew whoami`, `aew check run` and `aew submit` reach the engine through the run's bridge; anything else "
        "is the Lead's to run",
        entry_point=_declared, operation=operation, reason="non_writer_process")
