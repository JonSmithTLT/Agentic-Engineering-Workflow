"""One render of one prototype cell, in its own process (the pack-truth plan, reviewed CLEAR, §2.3).

Usage: python -B -X utf8 pt_cell.py <spec.json>

The spec names the cell's own state copy (``root``), the project and invocation in it, the role and mode, and whether
this process is hooked. The process may write only inside ``root`` (V11-3): every write, rename, removal, directory
creation and child process outside it is refused by an audit hook before it happens, and listed in the output. A hooked
process installs the provenance hook (``pt_hook``) before anything imports ``aew``.

It renders, in this order, through the product's own entry points:
- the worker help texts (`aew --help`, `aew check --help`, `aew check run --help`, `aew submit --help`,
  `aew whoami --help`), at 100 columns;
- `aew whoami`, and for a role that may run checks `aew check run guardrails` and its check log;
- harness mode: the launch contract's prompt (the preamble and the pack) and the OpenCode system text;
  manual mode: `aew context pack` and `aew context show`;
- `aew submit` of the cell's report.
It prints one JSON object: the texts, the ids the hook allocated, and the refused writes.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

HELPERS = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPERS))

REFUSED: list[str] = []
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
PATH_EVENTS = {  # audit event -> the indexes of its path arguments that are written
    "os.rename": (0, 1), "os.replace": (0, 1), "os.remove": (0,), "os.rmdir": (0,), "os.mkdir": (0,),
    "os.link": (1,), "os.symlink": (1,), "os.truncate": (0,), "os.chmod": (0,), "os.chown": (0,), "os.utime": (0,),
    "shutil.rmtree": (0,), "shutil.copyfile": (1,), "shutil.copytree": (1,), "shutil.move": (1,),
    "os.removexattr": (0,), "os.setxattr": (0,),
}


def _inside(path: Any, root: str) -> bool:
    if isinstance(path, int):  # an open descriptor: what it names was checked when it was opened
        return True
    p = os.path.normcase(os.path.realpath(os.fsdecode(path)))
    return p == root or p.startswith(root + os.sep)


def guard_writes(root: Path) -> None:
    """Refuse every write outside ``root`` (V11-3: the hooked process may write only to its own state copy)."""
    top = os.path.normcase(os.path.realpath(root))

    def refuse(event: str, target: Any) -> None:
        REFUSED.append(f"{event} {os.fsdecode(target) if not isinstance(target, int) else target}")
        raise PermissionError(f"pt_cell: a write outside the cell's state copy: {event} {target!r}")

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if event == "open":
            path, mode, flags = args
            writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or \
                (mode is None and isinstance(flags, int) and flags & WRITE_FLAGS)
            if writes and path is not None and not _inside(path, top):
                refuse(event, path)
        elif event in PATH_EVENTS:
            for i in PATH_EVENTS[event]:
                if i < len(args) and args[i] is not None and not _inside(args[i], top):
                    refuse(event, args[i])
        elif event == "subprocess.Popen":
            cwd = args[2] if len(args) > 2 and args[2] is not None else os.getcwd()
            if not _inside(cwd, top):
                refuse(event, cwd)

    sys.addaudithook(hook)


def cli(*argv: str) -> dict[str, Any]:
    """Run the `aew` CLI in this process; its exit code, stdout and stderr."""
    from aew.cli.main import main

    out, err = io.StringIO(), io.StringIO()
    code: Any = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return {"argv": list(argv), "code": code, "stdout": out.getvalue(), "stderr": err.getvalue()}


def render(spec: dict[str, Any]) -> dict[str, Any]:
    repo, inv, mode, workspace = Path(spec["repo"]), spec["invocation"], spec["mode"], spec["workspace"]
    os.environ["AEW_INVOCATION_TOKEN"] = spec["token"]
    texts: dict[str, Any] = {}
    for name, argv in (("help aew", ["--help"]), ("help check", ["check", "--help"]),
                       ("help check run", ["check", "run", "--help"]), ("help submit", ["submit", "--help"]),
                       ("help whoami", ["whoami", "--help"])):
        texts[name] = cli(*argv)
    texts["whoami"] = cli("-C", workspace, "whoami")
    if spec.get("check"):
        res = cli("-C", workspace, "check", "run", spec["check"])
        texts["check run"] = res
        log = json.loads(res["stdout"]).get("log") if res["code"] == 0 else None
        if log:
            texts["check log"] = {"code": 0, "stdout": (repo / ".aew" / log).read_text(encoding="utf-8"),
                                  "stderr": ""}
    os.environ.pop("AEW_INVOCATION_TOKEN")
    if mode == "harness":
        from aew.engine.api import Engine
        from aew.harness.opencode import projection

        eng = Engine.discover(repo)
        state = eng._k.store.read()
        contract = eng.harness_contract(state, inv, f"R-{inv}-1")
        texts["prompt"] = {"code": 0, "stdout": contract.prompt, "stderr": ""}
        texts["system text"] = {"code": 0, "stdout": projection.system_text(contract, []), "stderr": ""}
    else:
        texts["context pack"] = cli("-C", str(repo), "context", "pack", inv)
        texts["context show"] = cli("-C", str(repo), "context", "show", inv)
    os.environ["AEW_INVOCATION_TOKEN"] = spec["token"]
    texts["submit"] = cli("-C", workspace, "submit", "--kind", spec["kind"], "--file", spec["report"])
    os.environ.pop("AEW_INVOCATION_TOKEN")
    return texts


def main() -> int:
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]  (-I ignores PYTHONIOENCODING)
    os.environ["COLUMNS"] = "100"
    os.environ["TMP"] = os.environ["TEMP"] = os.environ["TMPDIR"] = str(Path(spec["root"]) / "tmp")
    os.chdir(spec["repo"])
    guard_writes(Path(spec["root"]))
    registry: dict[str, Any] = {}
    if spec["hooked"]:
        import pt_hook

        plants = {rel: {tuple(json.loads(k)): v for k, v in sites.items()}  # a node key, as JSON (pt_hook.node_keys)
                  for rel, sites in (spec.get("plants") or {}).items()}
        pt_hook.install(plants=plants, yaml_plants=spec.get("yaml_plants") or {})
        registry = {"units": pt_hook.REGISTRY.units, "values": pt_hook.REGISTRY.values}
    if spec.get("quoted"):
        _load_quoted(Path(spec["quoted"]))
    if spec.get("probe_write"):  # the read-only test's positive control: a write outside the copy, refused
        try:
            Path(spec["probe_write"]).write_text("a write outside the cell's state copy\n", encoding="utf-8")
        except PermissionError:
            pass
    texts = render(spec)
    sys.stdout.write(json.dumps({"texts": texts, "registry": registry, "refused": REFUSED}, ensure_ascii=True) + "\n")
    return 0


def _load_quoted(path: Path) -> None:
    """Load a test module's quoted copy of a product string into this process, as a test importing it would (the
    planted control's test-quoted copy, §2.3): only its ``QUOTED_COPY`` assignment runs."""
    import ast
    import types

    tree = ast.parse(path.read_text(encoding="utf-8"))
    body = [st for st in tree.body if isinstance(st, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "QUOTED_COPY" for t in st.targets)]
    module = types.ModuleType(path.stem)
    exec(compile(ast.Module(body, []), str(path), "exec"), module.__dict__)  # noqa: S102 (a test file's literal)
    sys.modules[path.stem] = module


if __name__ == "__main__":
    sys.exit(main())
