"""What `aew init` takes in its one call, before it pins (register E119; the designer's ruling of 2026-11-03, §1).

First configuration is the check command, the workers' model and their provider, given at the console and written
before the pin. Nothing is written after the pin except through adopt and the token, so no sibling of these flags
exists anywhere else. They never reach ``containment``, ``network``, ``upstreams``, ``checks.*.network``, a ``harness``
name, ``gates.yaml`` or ``guardrails.yaml``, and no flag takes a key. Nothing runs here: the check isn't run or probed,
and the model is checked structurally only, since the listing needs a launch.

This module only turns the flags into the text of the files: ``Engine.initialize`` checks those bytes and pins them.
"""

from __future__ import annotations

import copy
import math
import re
import shlex
from dataclasses import dataclass
from typing import Any

from aew.errors import UsageError
from aew.harness import contract as K
from aew.harness import models
from aew.harness.containment import netns
from aew.knowledge.manifest import DEFAULT_CHECKS
from aew.policy import execution as X
from aew.util import dump_yaml

# The flags, by the parser's dest: their one owner. `lead_broker.refuses_locally` refuses them in a Lead session.
FLAGS = {"check_command": "--check-command", "check_timeout": "--check-timeout", "model": "--model",
         "provider": "--provider"}
CHECK_ID, PROFILE = "unit", "default"  # `unit` is the only check these flags set, and the profile's one name
CHECKS_REL = "policy/checks.yaml"
DESCRIPTION = "set at aew init"
# A bare shell operator: there is no shell here, so each of these would reach the program as an argument.
OPERATORS = ("&&", "||", "|", ";", "<", ">")
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
HAND_EDIT = (f"`aew init` without these flags, `aew lead acquire --expect-rev 0`, the edit of .aew/{X.REL_PATH}, then "
             f"the operator's `aew manifest adopt --reason <reason> {K.EXPECT_REV}`")


def _refuse(reason: str, message: str, **details: Any) -> UsageError:
    return UsageError(message, reason=reason, **details)


def _outside_quotes(text: str) -> tuple[str, bool]:
    """``text``'s characters outside any quotes, and whether a backslash lies outside single quotes. It walks the text
    as it was typed, because a POSIX split has already spent the backslashes it would be asked about."""
    bare: list[str] = []
    backslash = False
    quote = ""
    for char in text:
        if quote == "'":
            quote = "" if char == "'" else quote
        elif quote == '"':
            backslash = backslash or char == "\\"
            quote = "" if char == '"' else quote
        elif char in "'\"":
            quote = char
        elif char == "\\":
            backslash = True
        else:
            bare.append(char)
    return "".join(bare), backslash


def parse_check_command(text: str) -> list[str]:
    """The argv of ``--check-command``: split as POSIX on every platform, with no shell. What each refusal names is
    what the operator means instead, since each of these would otherwise pin a broken command."""
    bare, backslash = _outside_quotes(text)
    if backslash:
        raise _refuse("check_command_backslash",
                      f"--check-command: {text!r} has a backslash outside single quotes, which this split would spend. "
                      "Write a path with `/`, the running Python as {python}, or put the text in single quotes")
    try:
        argv = shlex.split(text, posix=True)
    except ValueError as exc:
        raise _refuse("check_command_unparseable", f"--check-command: {text!r} does not parse: {exc}") from None
    if not argv or not argv[0]:
        raise _refuse("check_command_empty", "--check-command is empty: give the command that runs the project's tests")
    found = [op for op in OPERATORS if op in bare]
    if found or ASSIGNMENT.match(argv[0]):
        what = f"the shell operator {found[0]}" if found else f"the leading assignment {argv[0]}"
        raise _refuse("check_command_shell",
                      f"--check-command: {text!r} has {what}, and a check runs with no shell. Name the shell yourself: "
                      f"sh -c {shlex.quote(text)}")
    return argv


def _timeout(text: str) -> int | float:
    """``--check-timeout``, as a number the file can hold: whether it is above zero is the schema's rule, and it's
    checked with the rest of the bytes."""
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise _refuse("check_timeout_not_a_number", f"--check-timeout: {text!r} is not a number of seconds")
    return int(value) if value.is_integer() else value


def _provider_env(provider: str) -> tuple[str, ...]:
    """The provider rule, on the parsed provider whichever flag named it. The tables are the containment's own: a
    provider it has no address for would be refused at a contained launch anyway, which is why this is an alpha limit
    rather than a choice."""
    if provider in netns.CATALOG_ADDRESSED:  # its free models need no key, and a listed variable left unset refuses
        return ()
    name = netns.PROVIDER_KEY_ENV.get(provider)
    if name is None:
        raise _refuse("unknown_provider",
                      f"--model: provider {provider!r} isn't one this flag knows "
                      f"({', '.join(sorted(netns.PROVIDER_KEY_ENV))}). Another provider is a hand edit: {HAND_EDIT}, "
                      "naming its containment.network.upstreams entry there", provider=provider)
    return (name,)


@dataclass(frozen=True)
class FirstConfiguration:
    """The flags as parsed. Whatever is ``None`` wasn't given, and its file stays the template's."""

    argv: tuple[str, ...] | None
    timeout_s: int | float | None
    identity: models.ModelIdentity | None
    provider: str | None  # as typed
    model: str | None  # as typed
    provider_env: tuple[str, ...] = ()

    def files(self) -> dict[str, str]:
        """The text of each policy file the flags change, by its path under ``.aew``."""
        out: dict[str, str] = {}
        if self.argv is not None:
            out[CHECKS_REL] = self._checks_text()
        if self.identity is not None:
            out[X.REL_PATH] = self._execution_text()
        return out

    def _checks_text(self) -> str:
        checks = copy.deepcopy(DEFAULT_CHECKS)
        unit = checks["checks"][CHECK_ID]
        unit.update(configured=True, command=list(self.argv or ()), description=DESCRIPTION)
        if self.timeout_s is not None:
            unit["timeout_s"] = self.timeout_s
        return dump_yaml(checks)

    def _execution_text(self) -> str:
        """The template with its comments, and the four values it leaves open. Each line is anchored, so a line that
        moved fails here and never writes half a policy; YAML's own dumper quotes the values."""
        profile = {**({"provider": self.provider} if self.provider is not None else {}), "model": self.model}
        text = X.TEMPLATE
        for line, new in (("configured: false", "configured: true\n"),
                          ("profiles: {}", dump_yaml({"profiles": {PROFILE: profile}})),
                          ("  default: null", f"  default: {PROFILE}\n"),
                          ("provider_env: []", dump_yaml({"provider_env": list(self.provider_env)}))):
            anchored = f"\n{line}\n"
            if text.count(anchored) != 1:
                raise AssertionError(f"the execution template has {text.count(anchored)} lines {line!r}")
            text = text.replace(anchored, f"\n{new}")
        return text

    def report(self) -> dict[str, Any]:
        """What the result says was written. The command is shown as the argv it became."""
        out: dict[str, Any] = {}
        if self.argv is not None:
            out["check"] = {"id": CHECK_ID, "argv": list(self.argv),
                            "timeout_s": DEFAULT_CHECKS["checks"][CHECK_ID]["timeout_s"]
                            if self.timeout_s is None else self.timeout_s}
        if self.identity is not None:
            out["model"] = {"profile": PROFILE, **self.identity.as_dict()}
            out["provider_env"] = list(self.provider_env)
            if not self.provider_env:
                out["provider_note"] = (f"provider {self.identity.provider}: no variable was written, since its free "
                                        "models need none and a listed variable left unset refuses the launch. A paid "
                                        f"model of it takes the hand edit: {HAND_EDIT}")
        return out

    def next_step(self) -> str:
        """The result's ``next``, by what was given. A worker reads a key from the shell that launches it, and the
        Lead's relay needs it named, so one line covers both. An ``--acquire`` path shows no credential."""
        if self.argv is None or self.identity is None:  # at least one was given, or there would be no configuration
            missing, file = (("check command", CHECKS_REL) if self.argv is None else ("model", X.REL_PATH))
            return (f"this project still has no {missing}. Adding it now takes `aew lead acquire --expect-rev 0`, the "
                    f"edit of .aew/{file}, then the operator's `aew manifest adopt --reason <reason> {K.EXPECT_REV}`. "
                    "The two paths don't mix: a held seat refuses `aew opencode --acquire`")
        if not self.provider_env:
            return ("run `aew doctor`, then start the Lead with `aew opencode --acquire`. It holds the seat itself: a "
                    "seat already held refuses `--acquire`")
        var = self.provider_env[0]
        return (f"run `aew doctor`. Set {var} by the hidden form (bash: `read -rsp '{var}: ' {var}; echo; export "
                f"{var}`; PowerShell 7: `$env:{var} = Read-Host '{var}' -MaskInput`), then start the Lead with "
                f"`aew opencode --acquire --provider-env {var}`; a stored login (`opencode auth login`) is the "
                f"alternative for the Lead. A worker reads {var} from the shell that launches it, and the Lead's relay "
                "needs it named, so this covers both. It holds the seat itself: a seat already held refuses "
                "`--acquire`")


def from_flags(*, check_command: str | None, check_timeout: str | None, model: str | None,
               provider: str | None) -> FirstConfiguration | None:
    """The flags as parsed, or ``None`` when none was given (an init that stays byte-identical). Raises before anything
    is written."""
    if check_command is None and check_timeout is None and model is None and provider is None:
        return None
    if check_timeout is not None and check_command is None:
        raise _refuse("check_timeout_alone", "--check-timeout only goes with --check-command: it's the timeout of the "
                                             "check that flag sets")
    if provider is not None and model is None:
        raise _refuse("provider_alone", "--provider only goes with --model: it's the provider of the profile that flag "
                                        "sets")
    argv = tuple(parse_check_command(check_command)) if check_command is not None else None
    timeout = _timeout(check_timeout) if check_timeout is not None else None
    if provider == "":
        raise _refuse("provider_empty", "--provider is empty: name the provider, or leave it out and write the model "
                                        "as provider/model")
    identity = models.from_profile(provider, model, field="--model") if model is not None else None
    provider_env = _provider_env(identity.provider) if identity is not None else ()
    return FirstConfiguration(argv, timeout, identity, provider, model, provider_env)
