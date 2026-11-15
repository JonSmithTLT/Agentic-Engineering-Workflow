#!/usr/bin/env python3
"""Check the committed dashboard bundle against the frontend at HEAD."""

from __future__ import annotations

import json
import re
import subprocess

from import_build import CONTRACT_REL, ROOT, SCHEMA, STATIC, git, sha256

MANIFEST = (STATIC / "BUILD.json").relative_to(ROOT).as_posix()
INPUTS = ("web/package.json", "web/package-lock.json")


def main() -> int:
    record = json.loads(git("show", f"HEAD:{MANIFEST}"))
    if record["schema"] != SCHEMA:
        raise ValueError("unsupported dashboard build manifest")
    source = record["source"]["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("invalid dashboard source commit")
    git("merge-base", "--is-ancestor", source, "HEAD")

    older_web = record["source"]["web_tree"]
    older_contract = record["contract"]["sha256"]
    older_inputs = record["inputs"]
    if (
        record["source"]["tree"] != git("rev-parse", f"{source}^{{tree}}").decode().strip()
        or older_web != git("rev-parse", f"{source}:web").decode().strip()
        or record["contract"]["path"] != CONTRACT_REL
        or older_contract != sha256(git("show", f"{source}:{CONTRACT_REL}"))
        or older_inputs != {path: sha256(git("show", f"{source}:{path}")) for path in INPUTS}
    ):
        raise ValueError("dashboard build manifest disagrees with its recorded source")

    if (
        older_web == git("rev-parse", "HEAD:web").decode().strip()
        and older_contract == sha256(git("show", f"HEAD:{CONTRACT_REL}"))
    ):
        print(f"Packaged dashboard matches web/ and the API contract at HEAD (built from {source[:12]}).")
        return 0

    count = git("rev-list", "--first-parent", "--count", f"{source}..HEAD", "--", "web/", CONTRACT_REL).decode().strip()
    print(
        f"Packaged dashboard is stale. {count} mainline commits touching web/ or the API contract since {source[:12]}."
    )
    print("Build and verify a new production bundle, then import it with tools/dashboard/import_build.py.")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Cannot establish packaged dashboard freshness: {error}") from error
