"""The CLI: ``python tools/harness_qualify --binary <path> --out <dir>``.

Writes ``record.json``, ``diff.txt`` and ``report.txt`` to ``--out`` and prints the report. ``--write-fixtures`` writes
the fixtures the measured facts make into the fixtures folder (the bump's new fixtures). Exit 0 when every check that
ran passed and the facts match the pin, 1 when a check failed or a fact changed, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # run as `python tools/harness_qualify`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "harness_qualify"  # noqa: A001 (so the package's relative imports resolve)

from harness_qualify import FIXTURES, pack_for, report, run  # noqa: E402
from harness_qualify.core import ERROR, FAIL, write_fixtures  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="harness_qualify", description=__doc__.splitlines()[0])
    p.add_argument("--harness", default="opencode")
    p.add_argument("--binary", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--fixtures", type=Path)
    p.add_argument("--only", nargs="*", help="check ids to run")
    p.add_argument("--slow", action="store_true", help="also run the conformance suite and the containment self-test")
    p.add_argument("--keep", action="store_true", help="keep the private run folders (server logs)")
    p.add_argument("--write-fixtures", action="store_true")
    args = p.parse_args(argv)
    fixtures = args.fixtures or FIXTURES.get(args.harness)
    pack = pack_for(args.harness, fixtures)
    record, diff, fixture_rows, adopt = run(pack, args.binary, out=args.out, fixtures=fixtures, only=args.only,
                                            slow=args.slow, keep=args.keep)
    text = report(record, diff, fixture_rows, adopt)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "record.json").write_bytes((json.dumps({**record.to_json(), "diff": diff.lines(),
                                                        "fixtures": fixture_rows, "adoptable": adopt},
                                                       indent=1, sort_keys=True) + "\n").encode())
    (args.out / "diff.txt").write_bytes(("\n".join(diff.lines()) + "\n").encode())
    (args.out / "report.txt").write_bytes(text.encode())
    sys.stdout.write(text)
    if args.write_fixtures:
        sys.stdout.write("wrote: " + ", ".join(write_fixtures(pack, record.version, record.facts, fixtures)) + "\n")
    failed = any(r["status"] in (FAIL, ERROR) for r in record.checks)
    return 1 if failed or not diff.clean else 0


if __name__ == "__main__":
    sys.exit(main())
