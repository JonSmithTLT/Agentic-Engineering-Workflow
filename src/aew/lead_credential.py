"""How a command gets the Lead credential (STG-05 CS-4 addendum 12, ruling 2): never as a command-line value.

A value on a command line lands in the shell's history file, and so does an ``export`` line holding one. So:

* a command that needs the Lead credential takes it from ``AEW_LEAD_TOKEN`` (:data:`ENV`);
* without it, on the operator's own terminal, it asks at a hidden prompt (:func:`operator.ask_hidden`) and uses what
  is typed for that command only;
* off a terminal it refuses, and the refusal gives the per-session form for each shell (:data:`SECURE_FORMS`), which
  echoes nothing and leaves nothing in history. No text AEW shows offers a persistent variable or a startup-file line
  (the designer, 2026-10-30): :data:`PER_SESSION_WHY` says why;
* ``--token`` with a value is refused (:func:`token_value_refusal`), naming the prompt and the variable.

This covers the Lead credential. A provider key's refusal gives the same per-session forms for its own name
(:func:`forms`, ``agentenv.env_fix``). ``--invocation-token`` (a scripted role's credential) still takes a value: a
known limit, tracked in the register.

Inside an AEW session (a Lead session, the contained Lead, a worker's run: :func:`in_session`) nothing asks: the
contained Lead's harness has a terminal of its own, the relay's, and a prompt there would ask the operator to type the
credential into a process the agent started. A Lead session's Lead-authenticated commands go through its broker
instead; a worker's run has none, since a Lead command is the Lead's (:func:`session_kind` words the refusal for each).
The variables :func:`session_kind` reads are how AEW's own processes behave, never a boundary (``aew.process_kind``); so
the prompt also needs standard input to be the terminal, and it names who asked, as the operator's authorization
prompt does (:func:`operator.challenge`).

This module is the one place a command gets the credential from the operator (ITEMS 54 reuses it).
"""

from __future__ import annotations

import os
import sys

from aew.errors import UsageError

ENV = "AEW_LEAD_TOKEN"


def forms(name: str = ENV, label: str = "Lead token") -> dict[str, str]:
    """The per-session forms that set the secret variable ``name``, one per shell, asking with ``label``. The one
    owner of these forms: the Lead credential's (:data:`SECURE_FORMS`) and a provider key's (``agentenv.env_fix``).
    Each was run once as written, with a synthetic value, before it went into this text where the shell was at hand
    (Lead log #94)."""
    return {
        "bash": f"read -rsp '{label}: ' {name}; echo; export {name}",
        "PowerShell 7": f'$env:{name} = Read-Host "{label}" -MaskInput',
        "Windows PowerShell 5.1": f'$s = Read-Host "{label}" -AsSecureString; $env:{name} = '
                                  "[Runtime.InteropServices.Marshal]::PtrToStringBSTR("
                                  "[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)); Remove-Variable s",
    }


SECURE_FORMS = forms()
PER_SESSION_WHY = ("for this shell session only: a persistent variable reaches every process you start, and a "
                   "startup file is a plain file in your home directory, like history")

_prompted: str | None = None  # what the operator typed at this process's prompt: one command's, in memory only


def secure_forms(name: str = ENV) -> str:
    """The per-session forms for ``name``, one line each, as a refusal or a guide shows them."""
    shown = SECURE_FORMS if name == ENV else forms(name, name)
    return "\n".join(f"  {shell}: {form}" for shell, form in shown.items())


def how_to_set() -> str:
    """What a refusal says the operator can do instead of passing the credential."""
    return (f"run the command at your own terminal and AEW asks for it at a hidden prompt; or set {ENV} "
            f"{PER_SESSION_WHY}. These forms echo nothing and leave nothing in history:\n{secure_forms()}")


def session_kind(env: os._Environ[str] | dict[str, str] | None = None) -> str | None:
    """``"lead"`` inside a Lead session (its broker's coordinates, or the contained Lead's marker), ``"worker"`` inside
    a worker's run (its credential or bridge: the rest of ``contract.CREDENTIAL_ENV``, the Lead credential itself
    apart), None outside any AEW session."""
    from aew import process_kind
    from aew.harness.contract import CREDENTIAL_ENV
    from aew.harness.lead_broker import ENV_NAMES

    env = os.environ if env is None else env
    lead = (*ENV_NAMES, process_kind.LEAD_CONTAINED_ENV)
    if any(env.get(name) for name in lead):
        return "lead"
    if any(env.get(name) for name in CREDENTIAL_ENV if name not in lead and name != ENV):
        return "worker"
    return None


def in_session(env: os._Environ[str] | dict[str, str] | None = None) -> bool:
    """Whether this process runs inside an AEW session of either kind (:func:`session_kind`)."""
    return session_kind(env) is not None


def can_prompt() -> bool:
    """A hidden prompt is offered only to the operator at their own terminal: outside any AEW session, with standard
    input a terminal and a controlling terminal (or console) to read from."""
    from aew import operator

    try:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):  # a closed or replaced stream is no terminal
        interactive = False
    return interactive and not in_session() and operator.has_terminal()


def required(*, instead: str = "") -> str:
    """The Lead credential for this command: ``AEW_LEAD_TOKEN``, else what the operator types at the hidden prompt,
    else a refusal that says how to give it safely. ``instead`` names another way the command has (``--acquire``)."""
    global _prompted
    token = os.environ.get(ENV) or _prompted
    if token:
        return token
    alternative = f" Or {instead}." if instead else ""
    kind = session_kind()
    if kind == "worker":  # a worker's run has no broker and no terminal of its own (review of #316, m6)
        raise UsageError("Lead credential required, and nothing asks for it inside an AEW session: this is a worker's "
                         "run, and a Lead-authenticated command is the Lead's, not this run's. Say what it is needed "
                         "for in the evidence this run submits, and the Lead decides.",
                         reason="lead_credential_required", session="worker")
    if kind == "lead":
        raise UsageError("Lead credential required, and nothing asks for it inside an AEW session: its "
                         "Lead-authenticated commands go through the session's broker. Run this command at your own "
                         f"terminal instead.{alternative}", reason="lead_credential_required", session="lead")
    if not can_prompt():
        raise UsageError(f"Lead credential required: {how_to_set()}{alternative}",
                         reason="lead_credential_required", forms=dict(SECURE_FORMS))
    from aew import operator
    from aew.harness.procs import process_chain

    who = " <- ".join(process_chain()) or "unknown"
    typed = operator.ask_hidden(
        "\n==== AEW: THE LEAD CREDENTIAL ====\n"
        "This command needs the Lead credential, for this command only. What you type is not shown.\n"
        f"  requested by : {who}\n"
        "If you did not start this command yourself, press Enter to refuse.\n"
        f"{operator.RELAY_WARNING}\n"
        "Lead token: ", what="the Lead credential").strip()
    if not typed:
        raise UsageError("no Lead credential was entered", reason="lead_credential_required")
    _prompted = typed
    return typed


def optional() -> str | None:
    """The Lead credential where a command works without it (``message unseen`` records more with it): the variable
    only, never a prompt."""
    return os.environ.get(ENV) or _prompted or None


def take_prompted() -> str:
    """What this process's prompt took, handed over once and forgotten (a Lead session's broker holds it from then)."""
    global _prompted
    token, _prompted = _prompted or "", None
    return token


def token_value_refusal(*, lead_session: bool) -> UsageError:
    """``--token`` with a value: refused before anything runs, since the value is already on the command line."""
    if lead_session:
        return UsageError("--token takes no value: a credential on a command line lands in the shell's history, "
                          "and a Lead session holds the Lead credential already: run the command without it",
                          reason="token_on_command_line")
    return UsageError(f"--token takes no value: a credential on a command line lands in the shell's history. "
                      f"Instead, {how_to_set()}", reason="token_on_command_line", forms=dict(SECURE_FORMS))
