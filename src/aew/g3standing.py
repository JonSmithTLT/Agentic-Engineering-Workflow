"""G3's standing on this host: whether an owner may accept G3 consent here now (A-37 `G3-12`; the STG-03 hand-off's
addendum 7, ruling 2; the G3-C brief, PR C1).

One function computes it, and every reader prints what it says, so doctor, ``aew g3 request``, a held receipt's note
and a weaker launch's line all use one reason and one fix. Its conditions, in order, the first failure deciding:

  1. **G3 is installed on this host:** Linux (A-37 is a Linux profile), ``request.sock``'s path, and the confirmer at
     its install path (``G3-14``);
  2. **the project's policy keeps every launch contained:** its containment mode is ``required`` and its network mode
     ``proxy_only`` or ``isolated``, both read through the policy's pin, as every launch reads them. A project with no
     execution policy has none to judge, so it fails;
  3. **no weaker agent context was live on this host within the window,** in any project (``G3-06``'s window, owned
     by the register as ``WINDOW_S``), from the register of weaker contexts (:mod:`aew.harness.weaker_register`).

Condition 4, "G3 answers", is the owner's consume call itself (G3-C's PR C2). The readers that are not an owner add a
probe that consumes nothing (:func:`aew.g3client.probe`). The standing is computed per call and never cached.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# The confirmer's install path (G3-14), as `g3/install.sh`'s CONFIRM_LINK makes it: restated here, as the client
# restates REQUEST_SOCK, and held to the installer by a test
CONFIRMER = "/usr/local/bin/aew-g3-confirm"
INSTALL = "sudo sh g3/install.sh --operator <account> --wheelhouse <dir> --aew-wheel <aew-*.whl>"
# What a project's policy needs for its launches to count (condition 2), in the policy's own words
POLICY_FIX = "set containment.mode: required and containment.network.mode: proxy_only (or isolated) in the project's " \
             "execution policy"


@dataclass(frozen=True)
class Standing:
    """What :func:`standing` found. ``condition`` is the first one that failed (1 to 3), None when G3 counts;
    ``judged`` names the conditions this reader could judge (a reader with no project cannot judge condition 2)."""

    counts: bool
    condition: int | None = None
    reason: str | None = None
    fix: str | None = None
    judged: tuple[int, ...] = (1, 2, 3)

    def line(self) -> str:
        """The one line every reader prints."""
        if not self.counts:
            where = "for this project" if self.condition == 2 else "on this host"  # condition 2 is per project
            return f"G3 does not count {where}: {self.reason}. Fix: {self.fix}"
        if 2 not in self.judged:
            return ("G3 counts on this host for a project whose policy keeps every launch contained (containment "
                    "required, network proxy_only or isolated): condition 2 is per project, and not judged here")
        from aew.harness.weaker_register import WINDOW_S

        return ("G3 counts here: it is installed, this project's policy keeps every launch contained, and no weaker "
                f"agent context was live on this host in the last {WINDOW_S // 60} minutes")


def _fail(condition: int, reason: str, fix: str, judged: tuple[int, ...]) -> Standing:
    return Standing(False, condition, reason, fix, judged)


def installed(*, platform: str | None = None) -> tuple[str, str] | None:
    """Condition 1: None when G3 is installed on this host; otherwise its reason and fix."""
    from aew.g3client import REQUEST_SOCK

    if not (platform or sys.platform).startswith("linux"):
        return "G3 is not on this host: it is a Linux profile (A-37)", "none on this platform: G3 runs on Linux only"
    if not Path(REQUEST_SOCK).exists():
        return (f"G3 is not on this host: {REQUEST_SOCK} does not exist",
                f"install G3 as root ({INSTALL}), or start its service: sudo systemctl start aew-g3.service")
    if not Path(CONFIRMER).exists():
        return (f"the confirmer is not installed: {CONFIRMER} does not exist",
                f"install G3 again as root ({INSTALL})")
    return None


def contained_policy(policy: dict[str, Any] | None) -> tuple[str, str] | None:
    """Condition 2: None when the project's policy keeps every launch contained; otherwise its reason and fix.
    ``policy`` is as a launch reads it, through the pin (``Engine.execution_policy``)."""
    from aew.harness import containment
    from aew.harness.containment import netns
    from aew.harness.containment.layout import ISOLATED, PROXY_ONLY

    if policy is None:
        return "this project has no execution policy, so nothing says its launches run contained", POLICY_FIX
    mode = containment.mode(policy)
    if mode != containment.REQUIRED:
        return f"this project's policy lets launches run weaker (containment.mode: {mode})", POLICY_FIX
    network = netns.mode(policy)
    if network not in (PROXY_ONLY, ISOLATED):
        return (f"this project's policy runs contained launches on the network mode {network}, which does not "
                "count (G3-00)", POLICY_FIX)
    return None


def _at(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def no_weaker_context(now: float | None = None) -> tuple[str, str] | None:
    """Condition 3: None when no weaker agent context was live on this host in the window; otherwise its reason and
    fix. The register's sweep records first what has ended since its owner last wrote (a writer, so where this
    process cannot write the register, as inside a sandbox, the reading stands without it, which only holds longer)."""
    from aew.errors import AEWError
    from aew.harness import weaker_register as W

    try:
        W.sweep(now)
    except (AEWError, OSError):
        pass
    r = W.read(now=now)
    if r.clear:
        return None
    if r.unreadable:
        return (f"the register of weaker contexts cannot be read whole ({r.unreadable[0]})",
                f"check {W.root()} at your own terminal: every file there is AEW's")
    if r.created_epoch is None:
        return ("the register of weaker contexts has not been created on this host",
                f"run `aew doctor` at your own terminal, outside any sandbox; G3 counts {W.WINDOW_S // 60} minutes "
                "after it is created")
    if r.live:
        e = r.live[0]
        more = f" (and {len(r.live) - 1} more)" if len(r.live) > 1 else ""
        return (f"a weaker agent context is live on this host: {e['kind']} {e['id']} in {e['project'] or 'no project'}"
                f" ({e['why']}){more}",
                f"end it, or wait for it to end; G3 counts {W.WINDOW_S // 60} minutes after it ends")
    if r.recent:
        e = r.recent[0]
        return (f"a weaker agent context was live on this host in the last {W.WINDOW_S // 60} minutes: {e['kind']} "
                f"{e['id']} in {e['project'] or 'no project'} ({e['why']})",
                f"wait: G3 counts {W.WINDOW_S // 60} minutes after it ended")
    return (f"the register of weaker contexts was created at {r.created_at}, inside the last {W.WINDOW_S // 60} "
            "minutes, and its creation counts as a weaker context that ended then",
            f"wait until {_at(r.created_epoch + W.WINDOW_S)}")


def standing(policy: dict[str, Any] | None = None, *, project: bool = True, now: float | None = None,
             platform: str | None = None) -> Standing:
    """G3's standing for an owner's project (``project``: judge condition 2 from ``policy``), or, for a reader bound
    to no project (``project=False``), for conditions 1 and 3. Computed per call, never cached."""
    judged = (1, 2, 3) if project else (1, 3)
    failed = installed(platform=platform)
    if failed:
        return _fail(1, *failed, judged)
    if project:
        failed = contained_policy(policy)
        if failed:
            return _fail(2, *failed, judged)
    failed = no_weaker_context(now)
    if failed:
        return _fail(3, *failed, judged)
    return Standing(True, judged=judged)


def weaker_launch_line(*, kind: str, project: str | None) -> str | None:
    """What a weaker launch's line adds on a G3 host (addendum 7): when G3 counts again here, and, where the launch is
    weaker because its project's policy allows it, for that project while the policy says so. An eval lane is weaker
    whatever its project's policy says, so its line gives the host clause alone. None where G3 is not installed."""
    from aew.harness import weaker_register as W

    if installed() is not None:
        return None
    host = f"G3 counts on this host again {W.WINDOW_S // 60} minutes after this launch ends"
    lane = kind.startswith(("eval_", "dogfood_"))
    for_project = "" if lane or not project else f", and for {project} only while its policy keeps every launch " \
                                                  "contained"
    return (f"{host}{for_project}. An approval window you did not open is not yours to approve: decline it.")
