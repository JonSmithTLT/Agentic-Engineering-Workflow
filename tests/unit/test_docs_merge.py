"""Changes to different rows of the shared status documents merge without conflict (operator, 2026-10-09).

The register (`future-work.yaml`, rendered to `future-work.md` and `decisions-due.md` by `tools/register.py`) and
`implementation-status.md` are edited by most pull requests. Git's three-way merge conflicts where both sides change
the same or neighbouring lines. As one-line table rows, two pull requests that changed neighbouring rows always
conflicted in the markdown, even when the YAML merged (PR #142 against main, 2026-10-09), and GitHub's merge button
runs no local merge driver. Now every row is a block of its own, a heading and one paragraph per cell with blank lines
between, so an unchanged line always separates two rows.

These tests merge real files with real git (`git merge-tree`, the merge GitHub runs) in a scratch repository: changes
to neighbouring rows merge, and the merge is what rendering the merged YAML gives; the same cell changed on both sides
still conflicts, and the table layout conflicted on the same changes, so the tests are not vacuous; and the register
conflict of 2026-10-09 is replayed from this repository's history and no longer occurs.
"""

from __future__ import annotations

import copy
import functools
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("register", ROOT / "tools" / "register.py")
assert _spec is not None and _spec.loader is not None
register = importlib.util.module_from_spec(_spec)
sys.modules["register"] = register
_spec.loader.exec_module(register)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)  # the same data as safe_load, faster


def load(text: str) -> Any:
    return yaml.load(text, Loader=LOADER)  # noqa: S506  (a safe loader: CSafeLoader or SafeLoader)
REG_YAML, REG_MD = "docs/implementation/future-work.yaml", "docs/implementation/future-work.md"
DUE_YAML, DUE_MD = "docs/implementation/decisions-due.yaml", "docs/implementation/decisions-due.md"
STATUS = "docs/implementation/implementation-status.md"
STATUS_TEXT = (ROOT / STATUS).read_text(encoding="utf-8")
DATA = yaml.safe_load((ROOT / REG_YAML).read_text(encoding="utf-8"))
DUE = yaml.safe_load((ROOT / DUE_YAML).read_text(encoding="utf-8"))
# PR #142's merge of main (d40d802): its two parents, and their merge base.
PR142, MAIN, BASE142 = "be44a7f", "0ff0435", "099a4df"


class Repo:
    """A scratch repository with no system or global git configuration, whose commits are made from file contents."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir()
        (path.parent / "empty.gitconfig").write_text("", encoding="utf-8")
        self.env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(path.parent / "empty.gitconfig"),
                    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        self.git("init", "-q")

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.path, env={**os.environ, **self.env}, capture_output=True,
                              text=True, encoding="utf-8", check=check, creationflags=NO_WINDOW)

    def commit(self, files: dict[str, str], parent: str | None = None) -> str:
        for rel, text in files.items():
            (self.path / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.path / rel).write_text(text, encoding="utf-8", newline="\n")
        self.git("add", "-A")
        tree = self.git("write-tree").stdout.strip()
        return self.git("commit-tree", tree, *(["-p", parent] if parent else []), "-m", "c").stdout.strip()

    def merge(self, ours: str, theirs: str) -> tuple[list[str], dict[str, str]]:
        """The paths that conflict when ``theirs`` is merged into ``ours``, and every merged file's content."""
        out = self.git("merge-tree", "--write-tree", "--name-only", ours, theirs, check=False)
        assert out.returncode in (0, 1), out.stderr
        tree, _, rest = out.stdout.partition("\n")
        conflicted = rest.split("\n\n")[0].split() if out.returncode == 1 else []
        return conflicted, self.read(tree)

    def read(self, tree: str) -> dict[str, str]:
        """Every file of ``tree``, in two git calls."""
        listing = self.git("ls-tree", "-r", "-z", "--format=%(objectname) %(path)", tree).stdout.strip("\0")
        oids, paths = zip(*(entry.split(" ", 1) for entry in listing.split("\0")), strict=True)
        batch = subprocess.run(["git", "cat-file", "--batch"], cwd=self.path, env={**os.environ, **self.env},
                               input="\n".join(oids).encode() + b"\n", capture_output=True, check=True,
                               creationflags=NO_WINDOW).stdout
        files, at = {}, 0
        for path in paths:  # each object: "<oid> blob <size>\n<content>\n"
            end = batch.index(b"\n", at)
            size = int(batch[at:end].split()[2])
            files[path] = batch[end + 1:end + 1 + size].decode("utf-8")
            at = end + 2 + size
        return files


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "repo")


def register_files(data: dict[str, Any] | None = None, due: dict[str, Any] | None = None) -> dict[str, str]:
    """What `render` commits for this data (the real register by default): both YAML files normalized, both pages
    rendered."""
    if data is None and due is None:
        return dict(_real_register_files())
    data = register.normalize(copy.deepcopy(DATA if data is None else data))
    due = register.normalize_due(copy.deepcopy(DUE if due is None else due))
    return {REG_YAML: register.dump(data), REG_MD: register.render_markdown(data),
            DUE_YAML: register.dump(due), DUE_MD: register.render_due(due)}


@functools.cache
def _real_register_files() -> tuple[tuple[str, str], ...]:
    return tuple(register_files(DATA, DUE).items())


def section(data: dict[str, Any], number: int) -> dict[str, Any]:
    return next(s for s in data["sections"] if s["number"] == number)


def row(data: dict[str, Any], rid: str) -> dict[str, str]:
    return next(r for s in data["sections"] for r in s["rows"] if next(iter(r.values())) == rid)


def neighbours(data: dict[str, Any], number: int) -> tuple[str, str]:
    """Two neighbouring rows of a section, the first with a non-empty last cell: where changes to two different rows
    come closest (the first row's last line, the second row's first cell)."""
    rows = section(data, number)["rows"]
    last = section(data, number)["columns"][-1]
    a, b = next((a, b) for a, b in zip(rows, rows[1:], strict=False) if a[last])
    return next(iter(a.values())), next(iter(b.values()))


def changed(data: dict[str, Any], rid: str, column: str, text: str) -> dict[str, Any]:
    data = copy.deepcopy(data)
    row(data, rid)[column] += text
    return data


def merged_register(files: dict[str, str]) -> dict[str, Any]:
    return load(files[REG_YAML])


# ------------------------------------------------------------------------------------------------------- the register

def test_changes_to_neighbouring_register_rows_merge_and_equal_the_render_of_the_merged_yaml(repo):
    """The closest two changes to different rows can be: the last cell of one row and the first cell after the next
    row's heading."""
    first, second = neighbours(DATA, 2)
    columns = section(DATA, 2)["columns"]
    base = repo.commit(register_files())
    ours_data = changed(DATA, first, columns[-1], " Changed on our side.")
    theirs_data = changed(DATA, second, columns[1], " Changed on their side.")
    ours = repo.commit(register_files(ours_data), base)
    theirs = repo.commit(register_files(theirs_data), base)
    conflicts, files = repo.merge(ours, theirs)
    assert conflicts == []
    both = changed(ours_data, second, columns[1], " Changed on their side.")
    assert merged_register(files) == both
    assert files[REG_MD] == register.render_markdown(both), "the merged page is the page the merged YAML renders"


def test_closing_a_row_or_adding_one_beside_a_changed_neighbour_merges(repo):
    """The other everyday changes: a row moved to §Closed while its neighbour changes, and a row appended to a section
    whose last row changes."""
    first, second = neighbours(DATA, 2)
    closed = section(DATA, 9)
    base = repo.commit(register_files())
    closing = copy.deepcopy(DATA)
    section(closing, 2)["rows"].remove(row(closing, first))
    section(closing, 9)["rows"].append(dict(zip(closed["columns"], [first, "Moved here", "2026-10-09", "This test"],
                                                strict=True)))
    neighbour = changed(DATA, second, section(DATA, 2)["columns"][1], " Changed beside the closing.")
    conflicts, files = repo.merge(repo.commit(register_files(closing), base),
                                  repo.commit(register_files(neighbour), base))
    assert conflicts == []
    assert files[REG_MD] == register.render_markdown(merged_register(files))
    assert row(merged_register(files), second) == row(neighbour, second)

    rows = section(DATA, 2)["rows"]
    last_id, columns = next(iter(rows[-1].values())), section(DATA, 2)["columns"]
    adding = copy.deepcopy(DATA)
    section(adding, 2)["rows"].append({c: "" for c in columns} | {columns[0]: "F999", columns[1]: "New work",
                                                                   section(DATA, 2)["target_column"]: "**M6**"})
    last_changed = changed(DATA, last_id, next(c for c in reversed(columns) if rows[-1][c]), " Changed at the end.")
    conflicts, files = repo.merge(repo.commit(register_files(adding), base),
                                  repo.commit(register_files(last_changed), base))
    assert conflicts == []
    assert files[REG_MD] == register.render_markdown(merged_register(files))
    assert row(merged_register(files), "F999")[columns[1]] == "New work"


def test_neighbouring_decisions_due_items_merge(repo):
    """The closest two changes to different items: the last field of one and the first field of the next."""
    items = DUE["items"]
    base = repo.commit(register_files())
    ours_due, theirs_due = copy.deepcopy(DUE), copy.deepcopy(DUE)
    ours_due["items"][0]["blocks"] = [*(items[0].get("blocks") or []), "F3"]  # the item's last field
    theirs_due["items"][1]["needs"] = next(n for n in register.NEEDS if n != items[1]["needs"])  # its first field
    conflicts, files = repo.merge(repo.commit(register_files(DATA, ours_due), base),
                                  repo.commit(register_files(DATA, theirs_due), base))
    assert conflicts == []
    merged = load(files[DUE_YAML])
    assert merged["items"][0] == ours_due["items"][0] and merged["items"][1] == theirs_due["items"][1]
    assert files[DUE_MD] == register.render_due(merged)


def test_the_same_cell_changed_on_both_sides_still_conflicts(repo):
    first, _ = neighbours(DATA, 2)
    last = section(DATA, 2)["columns"][-1]
    base = repo.commit(register_files())
    conflicts, _ = repo.merge(repo.commit(register_files(changed(DATA, first, last, " Ours.")), base),
                              repo.commit(register_files(changed(DATA, first, last, " Theirs.")), base))
    assert sorted(conflicts) == [REG_MD, REG_YAML]


def test_the_table_layout_conflicted_on_the_same_neighbouring_changes(repo):
    """The control: the layout this replaced, one table line per row, conflicts on exactly the changes the block
    layout merges. Without it the merge tests above could pass for a reason other than the layout."""
    first, second = neighbours(DATA, 2)
    columns = section(DATA, 2)["columns"]

    def table(data: dict[str, Any]) -> dict[str, str]:
        rows = section(data, 2)["rows"]
        return {"table.md": "\n".join(["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
                                      + ["| " + " | ".join(r[c] for c in columns) + " |" for r in rows]) + "\n"}

    base = repo.commit(table(DATA))
    conflicts, _ = repo.merge(repo.commit(table(changed(DATA, first, columns[-1], " Ours.")), base),
                              repo.commit(table(changed(DATA, second, columns[1], " Theirs.")), base))
    assert conflicts == ["table.md"]


def git_show(spec: str) -> str | None:
    got = subprocess.run(["git", "-C", str(ROOT), "show", spec], capture_output=True, text=True, encoding="utf-8",
                         creationflags=NO_WINDOW)
    return got.stdout if got.returncode == 0 else None


def test_the_register_conflict_of_pr_142_against_main_no_longer_occurs(repo):
    """Replayed from history (a shallow clone without the commits skips; CI fetches all of it): PR #142 and main
    changed neighbouring rows (F15.2 against F15 and F15.3). The YAML merged and the table page conflicted; rendered
    in blocks, both sides' pages merge, into the page the merged YAML renders."""
    sides = {sha: (git_show(f"{sha}:{REG_YAML}"), git_show(f"{sha}:{REG_MD}")) for sha in (BASE142, PR142, MAIN)}
    if any(text is None for pair in sides.values() for text in pair):
        pytest.skip("PR #142's merge commits are not in this clone")

    def as_committed(sha: str, parent: str | None = None) -> str:
        return repo.commit({REG_YAML: sides[sha][0] or "", REG_MD: sides[sha][1] or ""}, parent)

    base = as_committed(BASE142)
    conflicts, _ = repo.merge(as_committed(PR142, base), as_committed(MAIN, base))
    assert conflicts == [REG_MD], "the replay reproduces the conflict of 2026-10-09"

    def as_rendered_now(sha: str, parent: str | None = None) -> str:
        data = register.normalize(load(sides[sha][0] or ""))
        return repo.commit({REG_YAML: register.dump(data), REG_MD: register.render_markdown(data)}, parent)

    base = as_rendered_now(BASE142)
    conflicts, files = repo.merge(as_rendered_now(PR142, base), as_rendered_now(MAIN, base))
    assert conflicts == []
    assert files[REG_MD] == register.render_markdown(register.normalize(merged_register(files)))


def old_layout(data: dict[str, Any]) -> dict[str, str]:
    """The register as committed before the block layout: the YAML without blank lines, a table per section."""
    data = register.normalize(copy.deepcopy(data))
    page = [f"# {data['title']}", "", data["preamble"], ""]
    for s in data["sections"]:
        page += [f"## {s['number']}. {s['title']}", "", *([s["intro"], ""] if s.get("intro") else []),
                 "| " + " | ".join(s["columns"]) + " |", "|" + "---|" * len(s["columns"]),
                 *("| " + " | ".join(r[c] for c in s["columns"]) + " |" for r in s["rows"]), ""]
    return {REG_YAML: yaml.dump(data, Dumper=register._Dumper, sort_keys=False, allow_unicode=True, width=118),
            REG_MD: "\n".join(page).rstrip("\n") + "\n"}


def test_resolve_finishes_merging_main_into_a_branch_from_before_the_block_layout(repo, capsys):
    """The pull requests open when the layout changed were written in the old one, so merging main into one conflicts
    in the register's page and YAML once. `register.py resolve` merges each YAML file again from its three sides, each
    in the canonical layout, and renders: both sides' changes, no conflict, nothing to merge by hand."""
    first, second = neighbours(DATA, 2)
    columns = section(DATA, 2)["columns"]
    due = {k: v for k, v in register_files().items() if k in (DUE_YAML, DUE_MD)}
    base = repo.commit(old_layout(DATA) | due)
    branch = repo.commit(old_layout(changed(DATA, first, columns[-1], " The branch's change.")) | due, base)
    main_data = changed(DATA, second, columns[1], " Main's change.")
    main = repo.commit(register_files(main_data), base)
    repo.git("checkout", "-q", "-f", "-B", "branch", branch)
    assert repo.git("merge", "-q", "--no-edit", main, check=False).returncode != 0, "the merge stops on the register"
    assert register.resolve(repo.path) == 0, capsys.readouterr().out
    for rel, text in register_files(changed(main_data, first, columns[-1], " The branch's change.")).items():
        assert (repo.path / rel).read_text(encoding="utf-8") == text, rel


# ------------------------------------------------------------------------------------------------ implementation status

CAPABILITY = re.compile(r"^### (.+)$", re.M)
FIELDS = ("**Status:** ", "**Acceptance evidence / next action:** ")


def capabilities(text: str) -> dict[str, list[str]]:
    """Each capability's paragraphs, in order."""
    found: dict[str, list[str]] = {}
    for block in re.split(r"\n(?=### )", text.split("\n## Capabilities\n", 1)[1])[1:]:
        heading, *paragraphs = [p for p in block.split("\n\n") if p.strip()]
        found[heading.removeprefix("### ")] = [p.strip("\n") for p in paragraphs]
    return found


def test_implementation_status_keeps_every_line_apart():
    """The layout that lets changes to different capabilities merge, hand-edited: no line touches another (every
    paragraph is one line, with blank lines between), no table, one section per capability with its Status and its
    evidence, and no 'Last updated' line that every change would edit."""
    lines = STATUS_TEXT.split("\n")
    touching = [f"{n}: {a[:60]}" for n, (a, b) in enumerate(zip(lines, lines[1:], strict=False), 1) if a and b]
    assert touching == [], "keep a blank line between every two lines of implementation-status.md"
    assert not [ln for ln in lines if ln.startswith("|")], "capabilities are sections, not table rows"
    assert "Last updated" not in STATUS_TEXT, "the history is `git log`; a date line conflicts between any two changes"
    names = CAPABILITY.findall(STATUS_TEXT)
    assert len(names) == len(set(names)), "one section per capability"
    for name, paragraphs in capabilities(STATUS_TEXT).items():
        assert [p[:len(f)] for p, f in zip(paragraphs, FIELDS, strict=False)] == list(FIELDS), (
            f"{name}: its first paragraphs are {FIELDS[0].strip()} and {FIELDS[1].strip()}")


def test_changes_to_neighbouring_capabilities_merge_and_the_same_field_still_conflicts(repo):
    names = list(capabilities(STATUS_TEXT))
    first, second = names[0], names[1]
    evidence = capabilities(STATUS_TEXT)[first][1]
    status = capabilities(STATUS_TEXT)[second][0]
    base = repo.commit({STATUS: STATUS_TEXT})
    ours = repo.commit({STATUS: STATUS_TEXT.replace(evidence, evidence + " Ours.", 1)}, base)
    theirs = repo.commit({STATUS: STATUS_TEXT.replace(status, status + " Theirs.", 1)}, base)
    conflicts, files = repo.merge(ours, theirs)
    assert conflicts == []
    both = STATUS_TEXT.replace(evidence, evidence + " Ours.", 1).replace(status, status + " Theirs.", 1)
    assert files[STATUS] == both
    other = repo.commit({STATUS: STATUS_TEXT.replace(evidence, evidence + " Theirs.", 1)}, base)
    conflicts, _ = repo.merge(ours, other)
    assert conflicts == [STATUS]
