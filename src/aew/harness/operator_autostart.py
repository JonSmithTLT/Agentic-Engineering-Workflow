"""`aew opencode` starts the project's operator endpoint itself, so one command starts a session.

It holds no authority: it starts ``aew operator serve --dev --background`` as a process of its own and never imports
the endpoint, which stays the one constructor of an ``OperatorPrincipal``. One endpoint per project: a live one is
reused, and one started at a terminal is never stopped. A background endpoint serves the sessions named in
``.aew/local/operator/sessions/`` and stops once none is live.

**Not a descendant of the session.** The endpoint refuses to start with a Lead session among its ancestors, and that
refusal stays. So this process applies the same check first, for what started it, and on Linux the endpoint is
reparented through a launcher that exits. The Lead's sandbox is built later, and the endpoint is outside it.

A start that fails never fails the session: without an endpoint the session runs as it did, and a request says how to
start one. ``AEW_OPERATOR_AUTOSTART=off`` turns it off, and the line a start prints says so.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aew.harness import contract, lead_broker, operator_client, procs

OFF_ENV = "AEW_OPERATOR_AUTOSTART"
LOG_NAME = "endpoint.log"  # the background endpoint's output: its start line and any failure, never a code
# The credentials: the endpoint uses none. The broker's coordinates stay, because the endpoint refuses on them.
SECRET_ENV = tuple(name for name in contract.CREDENTIAL_ENV if name not in lead_broker.ENV_NAMES)
# The launcher on Linux: a new session, then a fork whose parent exits, so the endpoint's parent is no Lead session.
REPARENT = "import os,sys;os.setsid();os._exit(0) if os.fork() else os.execv(sys.argv[1],sys.argv[1:])"
SW_HIDE, STARTF_USESHOWWINDOW, CREATE_NEW_CONSOLE = 0, 0x1, 0x10
START_FAILED = ("aew opencode: the operator endpoint did not start ({why}); a steering raise needs one: run "
                "`aew operator serve --dev` in another terminal\n")
NOT_HELD = START_FAILED.format(why="this session could not be named for it")


def endpoint_env(base: dict[str, str], provider_env: list[str]) -> dict[str, str]:
    """What the endpoint runs with: the operator's environment without the provider variables this session feeds or a
    Lead credential, and with its imports pinned to this engine. ``AEW_LEAD_BROKER`` stays if set: the endpoint refuses
    on it."""
    env = {k: v for k, v in base.items() if k not in SECRET_ENV and k not in provider_env}
    return procs.engine_imports(env)


def endpoint_argv(repo_root: Path) -> list[str]:
    return [sys.executable, *procs.ENGINE_PYTHON_FLAGS, "-m", "aew", "-C", str(repo_root), "operator", "serve", "--dev",
            "--background"]


def _start(argv: list[str], env: dict[str, str], log: Any) -> None:
    if sys.platform == "win32":  # pragma: windows-only
        # A console of its own, hidden: its window shows only when a challenge needs it (operator_window)
        info = subprocess.STARTUPINFO()
        info.dwFlags |= STARTF_USESHOWWINDOW
        info.wShowWindow = SW_HIDE
        subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, startupinfo=info,
                         creationflags=CREATE_NEW_CONSOLE)
        return
    command = [sys.executable, *procs.ENGINE_PYTHON_FLAGS, "-c", REPARENT, *argv]  # pragma: posix-only
    subprocess.run(command, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log)  # pragma: posix-only


def _refused(env: dict[str, str]) -> str | None:
    """The line for a session under a Lead session: it starts nothing and holds nothing."""
    problem = operator_client.lead_session_problem(env)
    return (f"aew opencode: the operator endpoint was not started: {problem}. To raise the steering mode, run `aew "
            "operator serve --dev` in your own terminal, outside this session\n") if problem else None


def ensure(engine: Any, *, provider_env: list[str], base: dict[str, str] | None = None) -> str | None:
    """Start the project's endpoint unless one is live. The line to show, or None when there is nothing to say."""
    env = dict(os.environ) if base is None else base
    if env.get(OFF_ENV) == "off":
        return None
    refused = _refused(env)
    if refused:
        return refused
    if operator_client.status(Path(engine.aew_root)).get("running"):
        return None
    directory = operator_client.locator_path(Path(engine.aew_root)).parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with open(directory / LOG_NAME, "ab") as log:  # two starts at once: the winner's line stays
            _start(endpoint_argv(Path(engine.repo_root)), endpoint_env(env, provider_env), log)
    except OSError as exc:
        return START_FAILED.format(why=exc)
    return (f"aew opencode: starting the operator endpoint in the background; it stops when no Lead session is left "
            f"(log: {Path(operator_client.LOCATOR_REL).with_name(LOG_NAME).as_posix()} under .aew; {OFF_ENV}=off turns "
            "this off)\n")


@contextlib.contextmanager
def for_session(engine: Any, *, provider_env: list[str]) -> Iterator[None]:
    """The endpoint for the length of one session: held while it runs, let go when it ends."""
    if os.environ.get(OFF_ENV) == "off":
        yield
        return
    held = None
    line = _refused(dict(os.environ))
    if not line:
        held = operator_client.name_session(Path(engine.aew_root))
        line = ensure(engine, provider_env=provider_env) if held else NOT_HELD
    if line:
        sys.stderr.write(line)
    try:
        yield
    finally:
        if held is not None:
            operator_client.unname_session(Path(engine.aew_root), held)
