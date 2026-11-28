"""Build the UAT story workload's starting repository: one script for the AEW run and the raw-harness run alike.

    python eval/experiments/uat-story/materialize.py <dest>

``<dest>`` must not exist. It becomes a git repository whose ``main`` is the starting point (Python-Markdown 3.11.0,
pinned by the lower-bound qualification lane's ``upstream.yaml``, plus that lane's seeded overlay without its failing
distractor test), and whose ``contrib/allowed-schemes`` branch is the contributor's change the workload asks the agent
to review (``fixture/contrib-branch/``). Commits are written with fixed names and dates, so every build of the same
inputs has the same commit ids: the AEW tree and the raw tree are identical when the printed ``main`` and branch
commits match.

The upstream base is taken from the lane's fetched copy when ``qualify.py fetch`` has run (its receipt must name the
pinned commit and tree), and otherwise cloned at the pinned tag into a temporary directory, refusing any other commit
or tree. Nothing here starts AEW: the runbook's next step is ``aew init`` in the AEW copy, and nothing in the raw copy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
LBQ = HERE.parent / "lower-bound-qualification"
UPSTREAM = LBQ / "upstream.yaml"  # the pin is the lane's: this workload restates none of it
LBQ_BASE, LBQ_RECEIPT = LBQ / "fixture" / "base", LBQ / "fixture" / "base.receipt.json"
LBQ_OVERLAY = LBQ / "fixture" / "overlay"
BRANCH_FILES = HERE / "fixture" / "contrib-branch"
BRANCH = "contrib/allowed-schemes"
# The lane's distractor is a test that fails on purpose. Here the project's configured check is the whole upstream
# suite, which must pass at the start, so the distractor is left out (README, "The starting tree").
LEFT_OUT = frozenset({"tests/test_syntax/extensions/test_wikilinks_spaces.py"})
# Tracked although upstream's .gitignore names *.egg-info/: a Ticket workspace is built from the commit, and without
# the in-tree metadata the upstream suite cannot resolve its extensions' entry points.
FORCE_ADD = ("Markdown.egg-info",)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
START = ("UAT Fixture", "fixture@example.invalid", "2026-11-30T09:00:00+00:00",
         "Starting point: Python-Markdown 3.11.0 with the link policy extension")
CONTRIB = ("Link Policy Contributor", "contributor@example.invalid", "2026-11-30T10:00:00+00:00",
           "Add an allow-list mode (allowed_schemes) to the link policy\n\nSites that only want a few schemes can "
           "now list them instead of listing every scheme to block.")


def git_env(identity: tuple[str, str, str, str] | None = None) -> dict[str, str]:
    """No inherited GIT_* variable and no system or global configuration; fixed author and dates when committing."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    if identity:
        name, email, date, _ = identity
        env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_AUTHOR_DATE=date, GIT_COMMITTER_NAME=name,
                   GIT_COMMITTER_EMAIL=email, GIT_COMMITTER_DATE=date)
    return env


def git(repo: Path, *args: str, identity: tuple[str, str, str, str] | None = None) -> str:
    return subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=", "-c", "commit.gpgsign=false",
                           *args], cwd=repo, check=True, capture_output=True, encoding="utf-8",
                          env=git_env(identity), stdin=subprocess.DEVNULL, creationflags=NO_WINDOW).stdout.strip()


def tree_files(root: Path) -> dict[str, bytes]:
    """Every regular file under ``root`` by relative path, LF line ends for text, without bytecode caches."""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and "__pycache__" not in rel.parts and p.suffix != ".pyc":
            data = p.read_bytes()
            out[rel.as_posix()] = data if b"\0" in data else data.replace(b"\r\n", b"\n")
    return out


def base_files(up: dict) -> tuple[dict[str, bytes], str]:
    """The pinned upstream's tracked files, and where they came from."""
    if LBQ_BASE.is_dir() and LBQ_RECEIPT.is_file():
        receipt = json.loads(LBQ_RECEIPT.read_text(encoding="utf-8"))
        if (receipt.get("commit"), receipt.get("tree")) != (up["commit"], up["tree"]):
            raise SystemExit(f"refused: the lane's fetched base is {receipt.get('commit')}, not the pinned "
                             f"{up['commit']}; run qualify.py fetch --again")
        files = tree_files(LBQ_BASE)
        source = f"the lane's fetched base ({LBQ_BASE})"
    else:
        with tempfile.TemporaryDirectory(prefix="aew-uat-story-fetch-") as tmp:
            clone = Path(tmp) / "clone"
            subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=", "clone", "--quiet",
                            "--depth", "1", "--branch", up["tag"], "--no-tags", up["url"], str(clone)], check=True,
                           env=git_env(), stdin=subprocess.DEVNULL, capture_output=True, creationflags=NO_WINDOW)
            commit, tree = git(clone, "rev-parse", "HEAD"), git(clone, "rev-parse", "HEAD^{tree}")
            if (commit, tree) != (up["commit"], up["tree"]):
                raise SystemExit(f"refused: {up['url']} {up['tag']} is commit {commit} tree {tree}, not the pinned "
                                 f"{up['commit']} {up['tree']}")
            tracked = [p for p in git(clone, "ls-files", "-z").split("\0") if p]
            files = {rel: (clone / rel).read_bytes() for rel in tracked}
            files = {rel: d if b"\0" in d else d.replace(b"\r\n", b"\n") for rel, d in files.items()}
        source = f"a clone of {up['url']} at {up['tag']}"
    if len(files) != up["file_count"]:
        raise SystemExit(f"refused: {len(files)} upstream files, the pin says {up['file_count']}")
    return files, source


def write(repo: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)


def commit(repo: Path, identity: tuple[str, str, str, str]) -> str:
    git(repo, "add", "-A")
    git(repo, "add", "-f", *FORCE_ADD)
    git(repo, "commit", "-q", "--no-verify", "-m", identity[3], identity=identity)
    return git(repo, "rev-parse", "HEAD")


def materialize(dest: Path) -> dict[str, str]:
    up = yaml.safe_load(UPSTREAM.read_text(encoding="utf-8"))
    base, source = base_files(up)
    overlay = {rel: d for rel, d in tree_files(LBQ_OVERLAY).items() if rel not in LEFT_OUT}
    if clash := sorted(set(base) & set(overlay)):
        raise SystemExit(f"refused: the overlay would replace upstream files: {clash}")
    if dest.exists():
        raise SystemExit(f"refused: {dest} exists; the starting tree is built into a new directory")
    dest.mkdir(parents=True)
    write(dest, {**base, **overlay})
    git(dest, "init", "-q", "--template=", "-b", "main")
    start = commit(dest, START)
    git(dest, "switch", "-q", "-c", BRANCH)
    write(dest, tree_files(BRANCH_FILES))
    contrib = commit(dest, CONTRIB)
    git(dest, "switch", "-q", "main")
    if git(dest, "status", "--porcelain"):
        raise SystemExit(f"refused: {dest} is not clean after the build")
    return {"repo": str(dest), "main": start, BRANCH: contrib, "upstream": source,
            "files_on_main": str(len(git(dest, "ls-files", "-z").split("\0")) - 1)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dest", type=Path, help="a new directory: the starting repository")
    args = parser.parse_args(argv)
    print(json.dumps(materialize(args.dest.resolve()), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
