"""`aew capability`: the capability register's commands (STG-15, A-38: CAPR-05, CAPR-13; the designer's CAP-1 ruling 1).

* `list` reads every capability's status on this host. `check` fetches what a record pins and the host lacks, checks
  each payload against its pin and runs the health checks; it changes no record or setting. Neither needs
  authorization; `check` is still never a Lead session's command (:func:`refuse_lead_session`).
* `import`, `add`, `remove` and `host-copies` change what every contained context gets, so they are the operator's:
  each sends one request to the project's operator endpoint (`aew operator serve --dev`), whose console shows the
  exact change and a code the operator types here. The endpoint applies the change it showed. They are on no agent's
  surface: the Lead broker refuses them (``lead_broker.OPERATOR_REGISTER``), no typed tool runs them, and the worker
  bridge offers no such operation.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from aew.cli.commands import _add_json, _engine
from aew.errors import OperatorAuthorizationRequired, PermissionDenied, UsageError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("capability", help="the capability register: the tools AEW brings to every contained run, "
                                          "their status on this host, and the operator's changes to them")
    csub = p.add_subparsers(dest="capability_cmd", required=True)
    q = csub.add_parser("list", help="every capability's status on this host, its provider, its cause and its fix")
    _add_json(q)
    q.set_defaults(handler=_list)
    q = csub.add_parser("check", help="fetch what a record pins and this host lacks, check every payload against its "
                                      "pin, and run the health checks")
    q.add_argument("selector", nargs="?", help="one provider (ripgrep) or capability (EXACT_CODE_SEARCH); default: all")
    q.add_argument("--offline", action="store_true", help="fetch nothing: check what is already on this host")
    _add_json(q)
    q.set_defaults(handler=_check)
    q = csub.add_parser("import", help="import pinned payloads from the operator's offline bundle (approved at the "
                                       "operator endpoint)")
    q.add_argument("bundle", help="a release archive, or a directory of them")
    _add_json(q)
    q.set_defaults(handler=lambda a: _change(a, "import", {"path": os.path.abspath(a.bundle)}))
    q = csub.add_parser("add", help="add an operator record, or override AEW's shipped record of the same name "
                                    "(validated, then approved at the operator endpoint)")
    q.add_argument("record_file", help="a YAML file of records (schema aew/capability-records/v1)")
    q.add_argument("--bundle", help="take the payload from this offline bundle instead of fetching it")
    _add_json(q)
    q.set_defaults(handler=_add)
    q = csub.add_parser("remove", help="remove an operator record; a shipped record it overrode serves again "
                                       "(approved at the operator endpoint)")
    q.add_argument("name", help="the provider's name")
    _add_json(q)
    q.set_defaults(handler=lambda a: _change(a, "remove", {"name": a.name}))
    q = csub.add_parser("host-copies", help="whether a copy the host has may serve where AEW's copy is absent or "
                                            "refused, named as unpinned (approved at the operator endpoint)")
    q.add_argument("setting", choices=["on", "off"])
    _add_json(q)
    q.set_defaults(handler=lambda a: _change(a, "host_copies", {"on": a.setting == "on"}))


def refuse_lead_session(command: str, environ: dict[str, str] | None = None) -> None:
    """A register command is never a Lead session's (CAPR-05). Keyed on the session's environment, so it is a
    keep-out, not authorization: the four changes take the operator endpoint's code besides."""
    from aew.engine.custody_ops import LEAD_SESSION, LEAD_SESSION_VARS

    present = [v for v in LEAD_SESSION_VARS if (environ if environ is not None else os.environ).get(v)]
    if present:
        raise PermissionDenied(f"`aew capability {command}` is the operator's, at their own terminal; it never runs "
                               f"in a Lead session ({', '.join(present)} present)", variables=present,
                               reason=LEAD_SESSION)


def _list(a: argparse.Namespace) -> Any:
    from aew.capability import ops

    view = ops.listing()
    return ops.public(view) if a.json else ops.render(view)


def _check(a: argparse.Namespace) -> Any:
    from aew.capability import ops

    refuse_lead_session("check")
    out = ops.check(a.selector, offline=a.offline)
    if a.json:
        return out
    said = [f"{name}: {line}" for name, lines in out["checked"].items() for line in lines]
    return "\n".join([*said, ops.render(out)])


def _add(a: argparse.Namespace) -> Any:
    from aew.capability import ops

    path = Path(a.record_file)
    try:
        with open(path, "rb") as fh:
            raw = fh.read(ops.MAX_RECORD_TEXT + 1)  # one past the limit is enough to refuse it
    except OSError as exc:
        raise UsageError(f"cannot read the record file {a.record_file}: {exc}", path=a.record_file) from None
    ops.check_record_size(raw, str(path))  # before anything is sent: the endpoint's request is bounded (F12)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UsageError(f"cannot read the record file {a.record_file}: {exc}", path=a.record_file) from None
    return _change(a, "add", {"text": text, "source": str(path),
                              "bundle": os.path.abspath(a.bundle) if a.bundle else None})


def _change(a: argparse.Namespace, kind: str, args: dict[str, Any]) -> Any:
    """Send one register change to the project's operator endpoint, and read the code the operator types here."""
    from aew import operator
    from aew.capability import ops
    from aew.harness import operator_client

    command = kind.replace("_", "-")
    refuse_lead_session(command)
    engine = _engine(a)  # the endpoint is the project's (`aew operator serve --dev`); the register is the host's
    if not operator.has_terminal():
        # Refused before the endpoint is contacted, as `aew lead mode raise`: a requester that cannot type the code
        # back never puts a challenge on the operator's console.
        raise OperatorAuthorizationRequired(
            f"`aew capability {command}` reads the confirmation code from your terminal, and this process has none (a "
            "harness tool call, a pipe or a scheduled job); run it yourself in a terminal, with the project's operator "
            "endpoint running in another (`aew operator serve --dev`)", detail="no terminal")
    out = operator_client.request_capability_change(engine.aew_root, kind, args)
    if a.json:
        return {**out, **ops.public(ops.listing())}
    return "\n".join([*out.get("change", []), f"applied; recorded at {out.get('recorded')}",
                      ops.render(ops.listing())])
