"""Sub-command registration. Handlers delegate to ``aew.engine.api.Engine``."""

from __future__ import annotations

import argparse
from typing import Any

from aew import doctor


def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="machine-readable output")


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("doctor", help="validate the environment and (if present) project state")
    _add_json(p)
    p.set_defaults(handler=_doctor)


def _doctor(args: argparse.Namespace) -> Any:
    report = doctor.run(cwd=args.cwd)
    return report if args.json else doctor.render(report)
