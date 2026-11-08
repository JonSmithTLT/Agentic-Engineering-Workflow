"""The generated reference pages merge: two pull requests that change different modules touch different lines, and a
collision on one module is settled by ``tools/reference.py resolve``, never by hand. Those pages conflicted on 47 of 61
merges of main into a branch in one week (2026-11-01 to 2026-11-08), 43 of them on ``modules.md``, each costing a push
and a CI run."""

from __future__ import annotations

import dataclasses
import difflib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("reference_under_merge_test", ROOT / "tools" / "reference.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)
common, _pages, _families = reference._families()
from reference_families import modules as M  # noqa: E402  (importable once _families() has set the path)

PAGE = "modules.md"
MODS = M.scan(common.Context(ROOT))
BY_NAME = {m.name: m for m in MODS}
ENGINE = [m.name for m in sorted(MODS, key=lambda m: m.name) if m.name.startswith("aew.engine.")]
BUSY = max(MODS, key=lambda m: len(m.imports)).name
# Two modules it does not import, with some it does import between them, as two far-apart changes would add.
_ABSENT = sorted(m.name for m in MODS if m.name not in BY_NAME[BUSY].imports and m.name != BUSY)
_FAR = [a for a in _ABSENT if any(a < i for i in BY_NAME[BUSY].imports)]
BUSY_ADDS = (_FAR[0], next(a for a in reversed(_ABSENT) if any(_FAR[0] < i < a for i in BY_NAME[BUSY].imports)))


class Repo:
    """A scratch repository whose commits are made from file contents."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "t")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "core.autocrlf", "false")

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=self.path, env=os.environ, capture_output=True, text=True,
                              encoding="utf-8", check=check, creationflags=NO_WINDOW)

    def commit(self, files: dict[str, str], parent: str | None = None) -> str:
        for rel, text in files.items():
            (self.path / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.path / rel).write_text(text, encoding="utf-8", newline="\n")
        self.git("add", "-A")
        tree = self.git("write-tree").stdout.strip()
        return self.git("commit-tree", tree, *(["-p", parent] if parent else []), "-m", "c").stdout.strip()

    def merged_page(self, ours: str, theirs: str) -> tuple[bool, str]:
        out = self.git("merge-tree", "--write-tree", ours, theirs, check=False)
        assert out.returncode in (0, 1), out.stderr
        tree = out.stdout.partition("\n")[0]
        return out.returncode == 0, self.git("show", f"{tree}:{PAGE}").stdout


def with_import(mods: list, name: str, *added: str, dropped: tuple[str, ...] = ()) -> list:
    """The modules with ``name``'s imports changed, as a pull request's code would change them."""
    return [dataclasses.replace(m, imports=tuple(sorted((set(m.imports) | set(added)) - set(dropped))))
            if m.name == name else m for m in mods]


def new_module(mods: list, name: str, *imports: str) -> list:
    return [*mods, M.Module(name, f"src/{name.replace('.', '/')}.py", False, tuple(sorted(imports)), ())]


def chain(mods: list, *changes) -> list:
    for change in changes:
        mods = change(mods)
    return mods


CASES = {
    "neighbours-in-one-group": (lambda m: with_import(m, ENGINE[10], "aew.util"),
                                lambda m: with_import(m, ENGINE[11], "aew.errors")),
    "one-gains-its-neighbour-loses": (lambda m: with_import(m, ENGINE[20], "aew.util"),
                                      lambda m: with_import(m, ENGINE[21], dropped=BY_NAME[ENGINE[21]].imports[:1])),
    "different-groups": (lambda m: with_import(m, "aew.cli.main", "aew.util"),
                         lambda m: with_import(m, ENGINE[0], "aew.errors")),
    "a-new-module-beside-a-change": (lambda m: new_module(m, "aew.engine.zz_new", "aew.util"),
                                     lambda m: with_import(m, ENGINE[-1], "aew.errors")),
    "new-modules-in-different-groups": (lambda m: new_module(m, "aew.engine.zz_new", "aew.util"),
                                        lambda m: new_module(m, "aew.cli.zz_new", "aew.errors")),
    "a-change-beside-the-group-heading": (lambda m: with_import(m, ENGINE[0], "aew.util"),
                                          lambda m: with_import(m, "aew.engine", "aew.errors")),
    # What 14 of the 15 collisions left in that week's replay were, while each module's imports were one line.
    "two-new-imports-on-one-busy-module": (lambda m: with_import(m, BUSY, BUSY_ADDS[0]),
                                           lambda m: with_import(m, BUSY, BUSY_ADDS[1])),
}


@pytest.mark.parametrize("case", CASES)
def test_two_prs_that_change_different_modules_merge_to_what_the_merged_code_renders(tmp_path, case):
    """Base `modules.md`, each side rendered from its own change, merged by git. No conflict, and the merged page is
    byte for byte the render of both changes together, so `check` passes with nothing to do."""
    one, other = CASES[case]
    repo = Repo(tmp_path / "repo")
    base = repo.commit({PAGE: M.page(MODS)})
    ours = repo.commit({PAGE: M.page(one(MODS))}, base)
    theirs = repo.commit({PAGE: M.page(other(MODS))}, base)
    clean, merged = repo.merged_page(ours, theirs)
    assert clean, merged[:2000]
    assert merged == M.page(chain(MODS, one, other))


def _block_of(lines: list[str], at: int) -> str:
    return next(line for line in reversed(lines[:at]) if line.startswith("### ")).strip("# `")


def test_a_change_to_one_modules_imports_rewrites_only_its_own_line():
    """Nothing on the page is drawn from another module, so a new import rewrites no other block: the importers column
    this replaced made one import change two modules' rows."""
    name = next(n for n in ENGINE if "aew.util" not in BY_NAME[n].imports)
    before = M.page(MODS).splitlines()
    after = M.page(with_import(MODS, name, "aew.util")).splitlines()
    added = list(difflib.ndiff(before, after))
    changed = [line for line in added if line.startswith(("- ", "+ "))]
    assert changed == ["+ - `aew.util`"], changed
    at = next(i for i, line in enumerate(after) if line == "- `aew.util`" and _block_of(after, i) == name)
    assert at, "the import is listed in its own module's block"


def test_the_module_page_holds_no_total_and_no_inverse_and_names_the_command_that_answers():
    page = M.page(MODS)
    assert "import edges" not in page and "Imported by" not in page and "(54)" not in page
    head = page.split("\n## ", 1)[0]
    assert "`python tools/reference.py importers <module>`" in head and "`python tools/reference.py counts`" in head


# Each of these lines collided in that week's merges: a tree-wide number on a page moves on nearly every pull request.
MEASURED_LINES = {
    "gaps.md": ("Unresolved items:",),
    "data-flow.md": ('function"|', 'functions"|', "records (coverage:", "(entry, function) pairs", " record)",
                     " records)"),
    "layout.md": ("Read sites found:",),
    "writers.md": ("Writer functions with a store-transaction", " writer functions ("),
    "interfaces.md": (" commands, each linked",),
}


@pytest.mark.parametrize("page", MEASURED_LINES)
def test_a_committed_page_holds_none_of_the_tree_wide_lines_that_collided(page):
    text = (ROOT / "docs" / "reference" / page).read_text(encoding="utf-8")
    assert not [line for line in MEASURED_LINES[page] if line in text]


def test_importers_answers_with_the_inverse_of_the_imports(capsys):
    target = next(m.name for m in sorted(MODS, key=lambda m: m.name) if M.importers_of(MODS, m.name))
    want = sorted(m.name for m in MODS if target in m.imports)
    assert reference.main(["importers", target]) == 0
    assert capsys.readouterr().out.split() == want


def test_importers_refuses_a_name_that_is_no_module_and_says_so_when_nothing_imports_one(capsys):
    assert reference.main(["importers", "aew.no_such_module"]) == 2
    assert "no module of src/aew" in capsys.readouterr().err
    lonely = next(m.name for m in MODS if not M.importers_of(MODS, m.name))
    assert reference.main(["importers", lonely]) == 0
    assert capsys.readouterr().out.strip() == f"nothing imports {lonely}"


@pytest.mark.parametrize("args", [["importers"], ["render", "aew.util"], ["check", "aew.util"]])
def test_only_importers_takes_a_module(args, capsys):
    with pytest.raises(SystemExit) as exc:
        reference.main(args)
    assert exc.value.code == 2


# ------------------------------------------------------------------------------------------------------------ resolve

def stopped_merge(tmp_path: Path, *, code_conflict: bool = False, tracked: tuple[str, ...] = ()) -> Repo:
    """A real `git merge` stopped on a collision in the same module's entry on the page."""
    repo = Repo(tmp_path / "repo")
    files = {"docs/reference/modules.md": "# Modules\n\nImports: a.\n", "src/code.py": "x = 1\n",
             **{name: "stale\n" for name in tracked}}
    base = repo.commit(files)
    ours = repo.commit({"docs/reference/modules.md": "# Modules\n\nImports: a, b.\n",
                        **({"src/code.py": "x = 2\n"} if code_conflict else {})}, base)
    theirs = repo.commit({"docs/reference/modules.md": "# Modules\n\nImports: a, c.\n",
                          **({"src/code.py": "x = 3\n"} if code_conflict else {})}, base)
    repo.git("update-ref", "refs/heads/main", ours)
    repo.git("reset", "-q", "--hard", ours)
    got = repo.git("merge", "--no-edit", theirs, check=False)
    assert got.returncode != 0, got.stdout
    return repo


@pytest.fixture
def rendering(monkeypatch):
    """`render` stands in for the merged code's render: `render` itself is tested with the real generator."""

    def render(root: Path, out: Path) -> list[str]:
        (out / "modules.md").write_text("# Modules\n\nImports: a, b, c.\n", encoding="utf-8", newline="\n")
        return ["modules.md"]

    monkeypatch.setattr(reference, "render", render)


def test_resolve_renders_and_stages_a_collision_on_a_module_and_the_merge_finishes(tmp_path, rendering, capsys):
    repo = stopped_merge(tmp_path)
    assert "docs/reference/modules.md" in repo.git("diff", "--name-only", "--diff-filter=U").stdout
    assert reference.resolve(repo.path) == 0
    assert repo.git("diff", "--name-only", "--diff-filter=U").stdout == ""
    assert (repo.path / "docs/reference/modules.md").read_text(encoding="utf-8") == "# Modules\n\nImports: a, b, c.\n"
    repo.git("commit", "-q", "--no-edit")
    assert "git commit" in capsys.readouterr().out


def test_resolve_stages_only_the_generators_pages_never_a_stray_file_beside_them(tmp_path, rendering):
    repo = stopped_merge(tmp_path)
    (repo.path / "docs/reference/stray.md").write_text("mine\n", encoding="utf-8")
    assert reference.resolve(repo.path) == 0
    assert "docs/reference/modules.md" in repo.git("diff", "--cached", "--name-only").stdout
    assert repo.git("status", "--porcelain", "--", "docs/reference/stray.md").stdout == "?? docs/reference/stray.md\n"


def test_resolve_settles_a_conflicted_page_the_render_did_not_change_and_a_removal_git_never_tracked(
        tmp_path, monkeypatch):
    """The two names that "stage what render returned" alone would get wrong: a page in conflict that already reads as
    rendered stays unmerged, and a stray file render deleted is unknown to git, which would stop `git add`."""
    repo = stopped_merge(tmp_path)

    def render(root: Path, out: Path) -> list[str]:
        (out / "modules.md").write_text("# Modules\n\nImports: a, b, c.\n", encoding="utf-8", newline="\n")
        return ["gone-stray.md"]  # it was removed, and modules.md counts as unchanged

    monkeypatch.setattr(reference, "render", render)
    assert reference.resolve(repo.path) == 0
    assert repo.git("diff", "--name-only", "--diff-filter=U").stdout == ""
    repo.git("commit", "-q", "--no-edit")


def test_resolve_stages_the_removal_of_a_tracked_page_with_a_non_ascii_name(tmp_path, monkeypatch):
    """git quotes such a name unless asked for `-z`, so it read as never tracked and stayed in the merge commit, where
    `check` then fails (review of #384, finding 6)."""
    stray = "stäle.md"
    repo = stopped_merge(tmp_path, tracked=(f"docs/reference/{stray}",))

    def render(root: Path, out: Path) -> list[str]:
        (out / "modules.md").write_text("# Modules\n\nImports: a, b, c.\n", encoding="utf-8", newline="\n")
        (out / stray).unlink()
        return ["modules.md", stray]

    monkeypatch.setattr(reference, "render", render)
    assert reference.resolve(repo.path) == 0
    repo.git("commit", "-q", "--no-edit")
    assert repo.git("ls-files", "-z", "--", "docs/reference/").stdout.split("\0") == ["docs/reference/modules.md", ""]


def test_two_first_edges_to_adjacent_groups_are_a_known_collision_that_resolve_settles(tmp_path):
    """A known residual: two pull requests in one group that each add a first edge to two alphabetically adjacent
    groups both insert at one place in the group's "Imports from the groups" list. Git stops there, as it should, and
    `resolve` settles it. If the page's form stops colliding here, this test says the residual has gone."""
    def package(name: str) -> M.Module:
        return M.Module(name, f"src/{name.replace('.', '/')}/__init__.py", True, (), ())

    mods = [package(f"aew.{group}") for group in ("a", "b", "c", "z")]
    mods += [new_module([], f"aew.a.{name}", "aew.z")[0] for name in ("first", "second", "third", "fourth")]
    repo = Repo(tmp_path / "repo")
    base = repo.commit({PAGE: M.page(mods)})
    ours = repo.commit({PAGE: M.page(with_import(mods, "aew.a.first", "aew.b"))}, base)
    theirs = repo.commit({PAGE: M.page(with_import(mods, "aew.a.fourth", "aew.c"))}, base)
    clean, merged = repo.merged_page(ours, theirs)
    assert not clean, "these two now merge: drop this residual"
    assert "<<<<<<<" in merged


def test_resolve_refuses_while_the_code_is_in_conflict_and_touches_nothing(tmp_path, rendering, capsys):
    """The code with its conflict markers is not what the pages should say."""
    repo = stopped_merge(tmp_path, code_conflict=True)
    before = (repo.path / "docs/reference/modules.md").read_bytes()
    assert reference.resolve(repo.path) == 2
    assert "src/code.py" in capsys.readouterr().err
    assert (repo.path / "docs/reference/modules.md").read_bytes() == before
    assert "docs/reference/modules.md" in repo.git("diff", "--name-only", "--diff-filter=U").stdout


def test_resolve_refuses_outside_a_merge(tmp_path, rendering, capsys):
    repo = Repo(tmp_path / "repo")
    repo.commit({"docs/reference/modules.md": "x\n"})
    assert reference.resolve(repo.path) == 2
    assert "no merge in progress" in capsys.readouterr().err
