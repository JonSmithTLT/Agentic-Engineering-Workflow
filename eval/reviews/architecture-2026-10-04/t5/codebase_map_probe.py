"""T5 probe: is a Git-object-based codebase map as cheap and reproducible as `T5-project-maps.md` §2 expects?

  python codebase_map_probe.py REPO [--commit H] [--out FILE] [--no-imports] [--repeat N]

Generates the `aew/codebase-map/v1` record of `T5-project-maps.md` §2 **from Git objects only** (`git ls-files` at the
commit, `git show <commit>:<path>` for the handful of files it reads): nothing is read from the working tree, so the
same commit in two different checkouts must give byte-identical records, and a dirty working tree cannot leak into a
map. `ignored_but_present` is the one section that needs the working tree (which untracked directories exist); it is
recorded as `null` with a note, which is a design observation for the note (§2 lists it; object-only generation cannot
have it).

Prints timings per section, the record's size, and a SHA-256 of the canonical YAML so runs can be compared across
checkouts and repeats. Read-only: it never writes into the repository.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import PurePosixPath

import yaml

LANG = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".jsx": "javascript",
        ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".c": "c", ".h": "c", ".cc": "c++",
        ".cpp": "c++", ".hpp": "c++", ".cs": "c#", ".rb": "ruby", ".php": "php", ".swift": "swift", ".sh": "shell",
        ".ps1": "powershell", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
        ".html": "html", ".css": "css", ".sql": "sql"}
ROLE_RULES = [  # first match wins; (regex over the directory path, role)
    (r"^(tests?|spec|__tests__)(/|$)", "tests"), (r"(^|/)(tests?|spec|__tests__)(/|$)", "tests"),
    (r"^(docs?|documentation)(/|$)", "docs"), (r"^\.github(/|$)", "ci"), (r"^(ci|\.gitlab)(/|$)", "ci"),
    (r"(^|/)(vendor|node_modules|third_party|external)(/|$)", "vendor"),
    (r"(^|/)(dist|build|target|out|generated|gen)(/|$)", "generated"),
    (r"^(src|lib|app|pkg|cmd|internal)(/|$)", "source"), (r"^(tools?|scripts?|bin)(/|$)", "build"),
    (r"^(config|conf|etc|policy|schemas?)(/|$)", "config"),
]
BUILD_FILES = {"pyproject.toml": "python/pyproject", "setup.py": "python/setuptools", "package.json": "node",
               "Cargo.toml": "rust/cargo", "go.mod": "go", "pom.xml": "java/maven", "build.gradle": "java/gradle",
               "CMakeLists.txt": "cmake", "Makefile": "make"}
SEMANTIC = ("compile_commands.json", "tsconfig.json", "pyrightconfig.json", ".clangd")
GENERATED_PATTERNS = (r"(^|/)(vendor|node_modules|dist|build|target)/", r"_pb2\.py$", r"\.generated\.", r"\.min\.js$")
TEST_FILE = re.compile(r"(^|/)(test_[^/]+\.py|[^/]+_test\.go|[^/]+\.spec\.[jt]sx?|[^/]+\.test\.[jt]sx?)$")
IMPORT_CAP = 500


class Repo:
    def __init__(self, path: str, commit: str | None) -> None:
        self.path = path
        self.commit = self.git("rev-parse", commit or "HEAD").strip()
        self.reads: list[str] = []

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", self.path, *args], capture_output=True, text=True, check=True,
                              encoding="utf-8", errors="replace").stdout

    def show(self, path: str) -> str | None:
        self.reads.append(path)
        try:
            return self.git("show", f"{self.commit}:{path}")
        except subprocess.CalledProcessError:
            return None

    def show_many(self, paths: list[str]) -> dict[str, str]:
        """One `git cat-file --batch` for many blobs: the import graph's cost depends on this, not on N `git show`s."""
        if not paths:
            return {}
        self.reads.extend(paths)
        spec = "".join(f"{self.commit}:{p}\n" for p in paths)
        out = subprocess.run(["git", "-C", self.path, "cat-file", "--batch"], input=spec.encode("utf-8"),
                             capture_output=True, check=True).stdout
        result: dict[str, str] = {}
        pos = 0
        for p in paths:
            nl = out.index(b"\n", pos)
            header = out[pos:nl].decode()
            pos = nl + 1
            if header.endswith("missing"):
                continue
            size = int(header.split()[-1])
            result[p] = out[pos:pos + size].decode("utf-8", errors="replace")
            pos += size + 1
        return result


def timed(section: str, fn, timings: dict[str, float]):
    t0 = time.perf_counter()
    value = fn()
    timings[section] = round((time.perf_counter() - t0) * 1000, 1)
    return value


def generate(repo: Repo, *, imports: bool) -> tuple[dict, dict[str, float]]:
    timings: dict[str, float] = {}
    # `git ls-files` lists the checkout's index, not the commit: the same commit in two checkouts on different branches
    # gave 809 and 930 files (first run of this probe). A commit-bound map reads the commit's tree.
    files = timed("ls_tree", lambda: [ln for ln in repo.git("ls-tree", "-r", "--name-only", "--full-tree",
                                                              repo.commit).split("\n") if ln], timings)
    record: dict = {"schema": "aew/codebase-map/v1", "source_revision": repo.commit, "tracked_files": len(files)}

    def directories():
        per_dir: dict[str, Counter] = defaultdict(Counter)
        for f in files:
            parts = PurePosixPath(f).parts
            for depth in (1, 2):
                if len(parts) > depth:
                    per_dir["/".join(parts[:depth])][PurePosixPath(f).suffix.lower()] += 1
        out = {}
        for d, exts in sorted(per_dir.items()):
            langs = Counter()
            for ext, n in exts.items():
                langs[LANG.get(ext, "other")] += n
            role = next((role for pat, role in ROLE_RULES if re.search(pat, d)), "unknown")
            out[d] = {"files": sum(exts.values()), "language": langs.most_common(1)[0][0], "role": role}
        return out
    record["directories"] = timed("directories", directories, timings)

    def languages():
        c = Counter(LANG.get(PurePosixPath(f).suffix.lower(), "other") for f in files)
        total = sum(c.values())
        return [{"language": lang, "files": n, "share": round(n / total, 3)} for lang, n in c.most_common(5)]
    record["languages"] = timed("languages", languages, timings)

    names = {f: PurePosixPath(f).name for f in files}
    record["build_system"] = timed("build_system", lambda: sorted(
        ({"system": BUILD_FILES[n], "file": f} for f, n in names.items() if n in BUILD_FILES), key=lambda x: x["file"]),
        timings)

    def entry_points():
        out = []
        pyproject = repo.show("pyproject.toml") if "pyproject.toml" in files else None
        if pyproject:
            in_scripts = False
            for line in pyproject.split("\n"):
                if line.strip().startswith("["):
                    in_scripts = line.strip() == "[project.scripts]"
                elif in_scripts and "=" in line:
                    name, target = (x.strip().strip('"') for x in line.split("=", 1))
                    out.append({"kind": "pyproject.scripts", "name": name, "target": target})
        if "package.json" in files:
            try:
                pkg = json.loads(repo.show("package.json") or "{}")
                for key in ("main", "bin"):
                    if key in pkg:
                        out.append({"kind": f"package.json.{key}", "target": pkg[key]})
            except json.JSONDecodeError:
                out.append({"kind": "package.json", "error": "unparseable"})
        for f in files:
            if names[f] in ("__main__.py", "main.go", "Program.cs") or f == "src/main.rs":
                out.append({"kind": "conventional", "file": f})
        return out
    record["entry_points"] = timed("entry_points", entry_points, timings)

    def test_locations():
        dirs = sorted({str(PurePosixPath(f).parent) for f in files if TEST_FILE.search(f)
                       or re.search(r"(^|/)(tests?|spec|__tests__)/", f)})
        runner = []
        if "pytest.ini" in files or ("pyproject.toml" in files and "[tool.pytest" in (repo.show("pyproject.toml") or "")):
            runner.append("pytest")
        if any(n.startswith("jest.config") for n in names.values()):
            runner.append("jest")
        if "go.mod" in files:
            runner.append("go test")
        return {"directories": dirs[:50], "directories_total": len(dirs), "runner": runner}
    record["test_locations"] = timed("test_locations", test_locations, timings)

    def generated_and_vendor():
        out = sorted({f for f in files if any(re.search(p, f) for p in GENERATED_PATTERNS)})
        attrs = repo.show(".gitattributes") if ".gitattributes" in files else None
        linguist = [ln.split()[0] for ln in (attrs or "").split("\n") if "linguist-generated" in ln]
        return {"paths": out[:50], "paths_total": len(out), "linguist_generated_patterns": linguist}
    record["generated_and_vendor"] = timed("generated_and_vendor", generated_and_vendor, timings)

    record["ignored_but_present"] = None
    record["notes"] = ["ignored_but_present needs the working tree (which ignored directories exist); an object-only "
                       "generation records null"]
    record["semantic_prerequisites"] = timed("semantic_prerequisites",
                                             lambda: sorted(f for f in files if names[f] in SEMANTIC), timings)

    if imports:
        def import_graph():
            py = [f for f in files if f.endswith(".py")]
            modules = {f: ".".join(PurePosixPath(f).with_suffix("").parts) for f in py}
            tops = {m.split(".")[0] for m in modules.values()} | {m.split(".")[1] for m in modules.values()
                                                                  if m.startswith(("src.", "lib."))
                                                                  and len(m.split(".")) > 1}
            bodies = repo.show_many(py)
            edges: dict[str, set[str]] = defaultdict(set)
            errors = 0
            for f, text in bodies.items():
                try:
                    tree = ast.parse(text)
                except SyntaxError:
                    errors += 1
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for a in node.names:
                            if a.name.split(".")[0] in tops:
                                edges[modules[f]].add(a.name)
                    elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                        if node.module.split(".")[0] in tops:
                            edges[modules[f]].add(node.module)
            capped = len(modules) > IMPORT_CAP
            return {"language": "python", "modules": len(modules), "edges": sum(len(v) for v in edges.values()),
                    "unparseable": errors, "capped": capped,
                    "graph": None if capped else {m: sorted(t) for m, t in sorted(edges.items())}}
        record["imports"] = timed("imports", import_graph, timings)
    else:
        record["imports"] = None

    record["observed_paths"] = sorted(set(repo.reads)) + ["<every tracked path: ls-files>"]
    return record, timings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--commit")
    ap.add_argument("--out")
    ap.add_argument("--no-imports", action="store_true")
    ap.add_argument("--repeat", type=int, default=3)
    a = ap.parse_args()
    repo = Repo(a.repo, a.commit)
    digests = []
    for i in range(a.repeat):
        repo.reads = []
        t0 = time.perf_counter()
        record, timings = generate(repo, imports=not a.no_imports)
        total = round((time.perf_counter() - t0) * 1000, 1)
        text = yaml.safe_dump(record, sort_keys=True, allow_unicode=True)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        digests.append(digest)
        if i == 0:
            print(f"repo={a.repo} commit={repo.commit} tracked={record['tracked_files']}")
            print(f"record: {len(text.encode('utf-8'))} bytes, {text.count(chr(10))} lines; sha256 {digest[:16]}")
            if record["imports"]:
                im = record["imports"]
                print(f"imports: {im['modules']} modules, {im['edges']} intra-repo edges, {im['unparseable']} unparseable, "
                      f"capped={im['capped']}")
            print(f"observed_paths (object reads): {len(record['observed_paths']) - 1} files + the ls-files listing")
            print("sections (ms): " + ", ".join(f"{k} {v}" for k, v in timings.items()))
            if a.out:
                with open(a.out, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
        print(f"run {i + 1}: total {total} ms, sha256 {digest[:16]}")
    print("deterministic across repeats:", len(set(digests)) == 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
