"""Select Windows integration and regression modules from the changed source and its Python import graph."""

from __future__ import annotations

import ast
import io
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import PurePosixPath

import tier
import yaml

# Never open a console window on Windows (the repository rule); 0 elsewhere, as tools/ci/tier.py does.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

WINDOWS_LINE = re.compile(r"sys\.platform|os\.name|win32|\bnt\b|msvcrt|ctypes|creationflags|os\.replace|lock|"
                         r"PermissionError|WinError", re.IGNORECASE)
SCOPED_DIRS = ("tests/integration/", "tests/regression/")
ROOTS = ("", "src/", "tests/", "tests/helpers/", "tools/", "tools/ci/", "g3/")
# External packages used in the repository's test environment. An unknown import is unresolved.
EXTERNAL = sys.stdlib_module_names | {"yaml", "pytest", "xdist", "coverage", "jsonschema", "referencing", "hypothesis",
                                      "psutil", "cryptography", "packaging", "clang", "pygments", "setuptools"}


def test_modules(sources: Mapping[str, str]) -> set[str]:
    return {p for p in sources if p.startswith(SCOPED_DIRS)
            and (PurePosixPath(p).match("test_*.py") or PurePosixPath(p).match("*_test.py"))}


def selected_modules(sources: Mapping[str, str], changed_lines: Mapping[str, Iterable[str]],
                     registered: set[str], *, fixture_independent: frozenset[str] = frozenset()) -> set[str]:
    """Return selected modules in this tree. Resolve old and new trees independently for a two-revision diff."""
    modules = test_modules(sources)
    selected = modules & (set(changed_lines) | registered)
    sensitive = {p for p, lines in changed_lines.items()
                 if p in sources and any(WINDOWS_LINE.search(line) for line in lines)}

    paths = set(sources)
    edges: dict[str, set[str] | None] = {}

    def dependencies(path: str) -> set[str] | None:
        if path in edges:
            return edges[path]
        try:
            nodes = ast.walk(ast.parse(sources[path], filename=path))
        except (ValueError, SyntaxError, RecursionError):
            edges[path] = None
            return None
        imports: set[str] = set()
        for node in nodes:
            dynamic_name = isinstance(node, ast.Name) and node.id in {"__import__", "exec", "eval"}
            loader = isinstance(node, ast.Attribute) and node.attr in {"import_module", "exec_module", "run_module"}
            loaders = {"import_module", "__import__", "run_module", "run_path"}
            loader_import = (isinstance(node, ast.ImportFrom) and node.module in {"importlib", "runpy", "builtins"}
                             and any(a.name in loaders for a in node.names))
            if dynamic_name or loader or loader_import:
                edges[path] = None
                return None
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            targets = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            relative = isinstance(node, ast.ImportFrom) and node.level
            if relative and relative > len(PurePosixPath(path).parents):
                edges[path] = None
                return None
            roots = (PurePosixPath(path).parents[relative - 1].as_posix() + "/",) if relative else ROOTS
            for name in targets:
                top = name.split(".")[0]
                base = name.replace(".", "/")
                found = False
                for root in roots:
                    prefix = (root + base).rstrip("/")
                    candidates = {prefix + ".py", prefix + "/__init__.py"}
                    if isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            member = prefix + "/" + alias.name
                            candidates.update((member + ".py", member + "/__init__.py"))
                    hits = candidates & paths
                    if hits:
                        found = True
                        imports.update(hits)
                        for hit in hits:
                            imports.update(str(parent / "__init__.py") for parent in PurePosixPath(hit).parents
                                           if str(parent / "__init__.py") in paths)
                if not found and (relative or top not in EXTERNAL):
                    edges[path] = None
                    return None
        edges[path] = imports
        return imports

    for module in sorted(modules - selected):
        pending = [module]
        if module not in fixture_independent:
            pending.extend(str(p / "conftest.py") for p in PurePosixPath(module).parents
                           if str(p / "conftest.py") in sources)
        seen: set[str] = set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            if path in sensitive:
                selected.add(module)
                break
            imports = dependencies(path)
            if imports is None:
                selected.add(module)
                break
            pending.extend(imports - seen)
    return selected


def select_change(base: Mapping[str, str], head: Mapping[str, str], changes: Mapping[str, Iterable[str]],
                  registered: set[str], *, fixture_independent: frozenset[str] = frozenset()) -> set[str]:
    """Keep each surviving module affected through either version of the graph, including a removed dependency."""
    return (selected_modules(base, changes, registered, fixture_independent=fixture_independent)
            | selected_modules(head, changes, registered, fixture_independent=fixture_independent)) & head.keys()


STORE_SUITES = frozenset({'tests/integration/test_history_store.py', 'tests/regression/test_log_sealing_model.py'})
# Public native qualification binds the ordinary suite, its local fixtures and the shared pytest configuration.
# A changed dependency needs new Windows evidence. A readme edit does not change these inputs.
QUALIFIED = ('d97f7bb42614019b581096e8a71c05805fed8fb2',)


def _driver(path: str) -> bool:
    name = PurePosixPath(path)
    return name.parent.as_posix() == 'tools/ci' and name.suffix == '.py' and name.stem.isidentifier()


def _unreferenced_driver(git: Callable[..., bytes], base: str, path: str) -> bool:
    source = ast.parse(git('show', f'{base}:{path}'))
    if not any(isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'" for node in source.body):
        return False
    try:
        references = git('grep', '-ilzF', '-e', PurePosixPath(path).stem, base, '--').split(b'\0')
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 1:
            return True
        raise
    return all(hit == f'{base}:{path}'.encode() for hit in references if hit)


def _fixture_context_changes(git: Callable[..., bytes], base: str, head: str) -> dict[str, str]:
    fields = git('diff', '--name-status', '--no-renames', '-z', base, head).decode().split('\0')[:-1]
    return dict(zip(fields[1::2], fields[::2], strict=True))


def _qualified_context(git: Callable[..., bytes], head: str, reference: str) -> bool:
    for path, status in _fixture_context_changes(git, reference, head).items():
        if path == 'tools/ci/windows_selection.py':  # the reviewed certificate and planner do not execute store tests
            continue
        if path == 'README.md' or (path.startswith('docs/') and path.endswith('.md')):
            continue
        if status != 'D' or not _driver(path) or not _unreferenced_driver(git, reference, path):
            return False
    return True


def qualified_modules(git: Callable[..., bytes], base: str, head: str, paths: list[str]) -> frozenset[str]:
    if not paths or not all(map(_driver, paths)) or any(os.environ.get(name) for name in
            ('AEW_HARNESS_ADAPTERS', 'PYTEST_PLUGINS', 'PYTEST_ADDOPTS')):
        return frozenset()
    try:
        changes = _fixture_context_changes(git, base, head)
        if set(changes) != set(paths) or any(kind != 'D' for kind in changes.values()):
            return frozenset()
        if not all(_unreferenced_driver(git, base, path) for path in paths):
            return frozenset()
        for reference in QUALIFIED:
            try:
                if _qualified_context(git, head, reference):
                    return STORE_SUITES
            except subprocess.CalledProcessError:
                continue  # a checkout without the qualifying revision uses the ordinary conservative walk
    except (OSError, UnicodeError, SyntaxError, ValueError, subprocess.SubprocessError):
        pass
    return frozenset()


def from_merge(merge: str, *, omit: bool = False) -> set[str]:
    """Read exact Git objects so removed imports and files participate in the same decision as additions."""
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "--literal-pathspecs", *args], creationflags=_NO_WINDOW)

    parents = git("rev-list", "--parents", "-n", "1", merge).decode().split()
    if len(parents) != 3:
        raise ValueError("expected a two-parent tested merge")
    head, base, _ = parents
    paths = git("diff", "--name-only", "-z", "--no-renames", base, head).decode().split("\0")[:-1]
    # Changes to expected skips and discovery outputs require the complete Windows evidence.
    if not paths:
        raise ValueError("empty PR diff")
    expectations = {"tests/platform-skips.yaml", "tests/helpers/discovery/allowed.yaml",
                    "tests/helpers/discovery/modes.py"}
    if omit and (expectations.intersection(paths) or
                 tier.FLAKE_REGISTER in paths and not tier.verified_register_edit(merge)):
        return set()
    changes = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        patch = git("diff", "--no-renames", "--no-ext-diff", "--no-textconv", "--text", "-U0",
                    base, head, "--", path).decode()
        changes[path] = [line[1:] for hunk in patch.split("\n@@ ")[1:] for line in hunk.splitlines()[1:]
                         if line.startswith(("+", "-"))]

    def sources(rev: str) -> dict[str, str]:
        files = {}
        for entry in git("ls-tree", "-r", "-z", rev).split(b"\0"):
            if entry.endswith(b".py"):
                header, path = entry.split(b"\t", 1)
                mode, kind, oid = header.split()
                if kind != b"blob" or mode not in {b"100644", b"100755"}:
                    raise ValueError("unresolved Python source")
                files[path.decode()] = oid
        data = subprocess.check_output(["git", "cat-file", "--batch"], input=b"\n".join(files.values()) + b"\n",
                                       creationflags=_NO_WINDOW)
        stream = io.BytesIO(data)
        result = {}
        for path, oid in files.items():
            identity, kind, size = stream.readline().split()
            if identity != oid or kind != b"blob":
                raise ValueError("unresolved Git object")
            result[path] = stream.read(int(size)).decode("utf-8-sig")
            if stream.read(1) != b"\n":
                raise ValueError("incomplete Git object")
        return result

    registry = yaml.safe_load(git("show", f"{head}:tests/flake-register.yaml"))
    if registry["schema"] != "aew/flake-register/v1" or not isinstance(registry["entries"], list):
        raise ValueError("invalid flake register")
    nodes = []
    for row in registry["entries"]:
        if row.get("test"):
            nodes.append(row["test"])
        if row.get("closure", {}).get("test"):
            nodes.append(row["closure"]["test"])
        for evidence in row["evidence"]:
            nodes.extend(evidence.get("nodes", []))
    registered = {node.split("::", 1)[0] for node in nodes}
    after = sources(head)
    independent = qualified_modules(git, base, head, paths)
    picked = select_change(sources(base), after, changes, registered, fixture_independent=independent)
    return test_modules(after) - picked if omit else picked


def for_pull_request(event: str, base_ref: str, merge: str, run_tier: str, repo: str, pr: str,
                     *, omit: bool = False) -> set[str] | None:
    """None means all Windows tests. Only a full-tier PR with known, unforced inputs can narrow its heavy lanes."""
    if event != "pull_request" or base_ref != "main" or run_tier != "full":
        return None
    trailer = tier.forced_by_trailer(merge)
    labels = tier.live_labels(repo, pr)
    if trailer is not False or labels is None or tier.FORCE_LABEL in labels:
        return None
    try:
        return from_merge(merge, omit=omit)
    except (OSError, subprocess.SubprocessError, LookupError, ValueError, TypeError, AttributeError,
            yaml.YAMLError) as exc:
        print(f"Windows selection could not be resolved ({type(exc).__name__}); running all modules", file=sys.stderr)
        return None


def omitted_for_workflow(pr: str, run_tier: str) -> set[str]:
    if not pr:
        return set()
    return for_pull_request(os.environ.get("GITHUB_EVENT_NAME", ""), os.environ.get("GITHUB_BASE_REF", ""),
                            os.environ.get("GITHUB_SHA", ""), run_tier, os.environ.get("GITHUB_REPOSITORY", ""),
                            pr, omit=True) or set()
