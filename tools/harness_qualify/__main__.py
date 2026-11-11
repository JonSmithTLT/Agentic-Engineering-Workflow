"""The CLI: ``python tools/harness_qualify --binary <path> --out <dir>``.

Writes ``record.json`` (the core's :func:`~harness_qualify.core.document`), ``diff.txt`` and ``report.txt`` to
``--out`` and prints the report. ``--write-fixtures`` writes the fixtures the measured facts make into the fixtures
folder (the bump's new fixtures). ``--no-network`` runs the tool under ``bwrap --unshare-net`` (loopback only), which
needs bubblewrap; without it egress is not blocked, and the record says so.

``--reevaluate <retained-record> --ruling <cited-ruling>`` is offline: no binary/server/model runs. Only the ruled
Linux retry predicate is recomputed from retained envelopes; other verdicts and runtime provenance remain. With
``--write-fixtures`` it writes only the messaging semantic pin, and only when all ten required checks pass.

Exit codes: 0 every binary check that ran passed and the facts match the pin; 1 a binary check failed or a fact
changed; 2 a usage error (an ``--only`` id that is no check, or ``--no-network`` without bubblewrap); 3 no binary check
ran, so nothing was qualified. A host-scoped check (the containment self-test) is reported apart and never sets it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as `python tools/harness_qualify`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "harness_qualify"  # noqa: A001 (so the package's relative imports resolve)

from harness_qualify import FIXTURES, pack_for, report, run  # noqa: E402
from harness_qualify.core import (  # noqa: E402
    EXIT_USAGE,
    NETWORK_BLOCKED_ENV,
    NetworkIsolationError,
    UnknownCheck,
    document,
    exit_code,
    has_bubblewrap,
    write_fixtures,
)


def _without_network(argv: list[str]) -> int:
    """This same command under ``bwrap --unshare-net``: a network namespace with loopback only, the host's filesystem
    as it is."""
    rest = [a for a in argv if a != "--no-network"]
    cmd = ["bwrap", "--unshare-net", "--dev-bind", "/", "/", "--proc", "/proc", "--",
           sys.executable, str(Path(__file__).resolve().parent), *rest]
    return subprocess.run(cmd, env={**os.environ, NETWORK_BLOCKED_ENV: "1"}).returncode


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="harness_qualify", description=__doc__.splitlines()[0])
    p.add_argument("--harness", default="opencode")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--binary", type=Path)
    source.add_argument("--reevaluate", type=Path, help="re-evaluate the retained Linux record without a runtime")
    p.add_argument("--ruling", type=Path, help="the cited Lead ruling for offline re-evaluation")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--fixtures", type=Path)
    p.add_argument("--only", nargs="*", help="check ids to run")
    p.add_argument("--slow", action="store_true", help="also run the conformance suite and the containment self-test")
    p.add_argument("--keep", action="store_true", help="keep the private run folders (server logs)")
    p.add_argument("--write-fixtures", action="store_true")
    p.add_argument("--no-network", action="store_true", help="run under bwrap --unshare-net (needs bubblewrap)")
    args = p.parse_args(argv)
    if args.reevaluate is not None:
        if args.harness != "opencode" or args.ruling is None or args.only is not None or any(
                (args.slow, args.keep, args.no_network)):
            p.error("--reevaluate needs --ruling; no binary, selection, slow, keep or network run options")
        from harness_qualify import reevaluate

        try:
            return reevaluate.run(args.reevaluate, args.ruling, out=args.out,
                                  fixtures=args.fixtures or FIXTURES[args.harness], write_pin=args.write_fixtures)
        except (ValueError, OSError) as exc:
            sys.stderr.write(f"{exc}\n")
            return EXIT_USAGE
    if args.ruling is not None:
        p.error("--ruling is only for --reevaluate")
    if args.no_network and os.environ.get(NETWORK_BLOCKED_ENV) != "1":
        if not has_bubblewrap() or not shutil.which("bwrap"):
            sys.stderr.write("--no-network needs bubblewrap (bwrap) on Linux; run without it, and the record says "
                             "egress was not blocked\n")
            return EXIT_USAGE
        return _without_network(argv)
    fixtures = args.fixtures or FIXTURES.get(args.harness)
    pack = pack_for(args.harness, fixtures)
    try:
        record, diff, fixture_rows, adopt = run(pack, args.binary, out=args.out, fixtures=fixtures, only=args.only,
                                                slow=args.slow, keep=args.keep)
    except (UnknownCheck, NetworkIsolationError) as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_USAGE
    text = report(record, diff, fixture_rows, adopt)
    args.out.mkdir(parents=True, exist_ok=True)
    doc = document(record, diff, fixture_rows, adopt)
    (args.out / "record.json").write_bytes((json.dumps(doc, indent=1, sort_keys=True) + "\n").encode())
    (args.out / "diff.txt").write_bytes(("\n".join(diff.lines()) + "\n").encode())
    (args.out / "report.txt").write_bytes(text.encode())
    sys.stdout.write(text)
    if args.write_fixtures:
        sys.stdout.write("wrote: " + ", ".join(write_fixtures(pack, record.version, record.facts, fixtures)) + "\n")
    return exit_code(record, diff)


if __name__ == "__main__":
    sys.exit(main())
