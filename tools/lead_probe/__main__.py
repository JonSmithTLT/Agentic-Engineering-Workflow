"""Run the Linux-only lead probe in a verified loopback-only namespace."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from harness_qualify.core import aew_revision, private_env, sha256_file  # noqa: E402

import aew  # noqa: E402
from aew.harness.opencode.capabilities import LEAD_PROBE_LINUX_X64_SHA256, TESTED_VERSIONS  # noqa: E402
from aew.harness.opencode.projection import lead_provider_policies  # noqa: E402
from lead_probe import network  # noqa: E402

REEXEC = "AEW_LEAD_PROBE_IN_NAMESPACE"
LEGS = ("lead", "worker", "listchanged")
HOLD = "Windows is not supported by this probe."


def pinned_sha(version: str = TESTED_VERSIONS[0]) -> str:
    sha = LEAD_PROBE_LINUX_X64_SHA256.get(version, "")
    if not re.fullmatch(r"[a-f0-9]{64}", sha):
        raise ValueError(f"no valid Linux x64 probe hash for OpenCode {version} in opencode/capabilities.py")
    return sha


def verify_package(imported_file: Path) -> None:
    source = (ROOT / "src/aew").resolve()
    installed = imported_file.resolve().parent
    if installed == source:
        return

    def files(root: Path) -> dict[Path, Path]:
        return {p.relative_to(root): p for p in root.rglob("*") if p.is_file()
                and "__pycache__" not in p.parts and p.suffix != ".pyc"}

    expected, actual = files(source), files(installed)
    if not expected or expected.keys() != actual.keys() or any(
        sha256_file(path) != sha256_file(actual[rel]) for rel, path in expected.items()
    ):
        raise ValueError("imported aew differs from the named checkout. Install that checkout into the probe Python.")


def run_binary(binary: Path, env: dict[str, str], cwd: Path, *args: str) -> str:
    result = subprocess.run([str(binary), *args], env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=90, check=False)
    if result.returncode:
        raise ValueError(f"OpenCode {args[0]} exited {result.returncode}")
    return result.stdout.decode("utf-8")


def pinned_version(display: str) -> str:
    version = display.strip().removeprefix("opencode v")
    if version not in TESTED_VERSIONS:
        raise ValueError(f"unqualified OpenCode version {display!r}")
    return version


def catalog(binary: Path, work: Path, env: dict[str, str]) -> list[str]:
    raw = run_binary(binary, env, work, "models")
    (work / "models.txt").write_text(raw, encoding="utf-8", newline="")
    providers = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        if not re.fullmatch(r"[\w.-]+/[^/\s]+(?:/[^/\s]+)*", line):
            raise ValueError(f"unparsed OpenCode models line {line!r}; see catalog/models.txt")
        providers.add(line.split("/", 1)[0])
    if "opencode" not in providers:
        raise ValueError("the pinned catalog did not report its known keyless control provider")
    return sorted(providers)


def prove_catalog(providers: list[str]) -> list[str]:
    denies = sorted({rule["resource"] for rule in lead_provider_policies()
                     if rule["action"] == "provider.use" and rule["effect"] == "deny"})
    if missing := set(providers) - set(denies):
        raise ValueError(f"keyless catalog providers missing from the deny policy: {', '.join(sorted(missing))}")
    return denies


def record(commit: str, version: str, sha: str, proof: dict, providers: list[str], denies: list[str]) -> dict:
    return {
        "schema": "aew/lead-probe/v1", "aew_commit": commit,
        "opencode": {"version": version, "sha256": sha, "pinned": True, "keyless_providers": providers,
                     "provider_denies": denies, "catalog_source": "catalog/models.txt (fresh keyless home)"},
        "network": proof, "legs": {}, "windows": "not run", "codex": "not run",
        "measurement": ("Provider parts are compact UTF-8 JSON with ensure_ascii=False, plus the difference from "
                        "the actual wire length. MCP advertised bytes use ensure_ascii=True."),
    }


def measure(binary: Path, out: Path, legs: list[str], proof: dict) -> None:
    verify_package(Path(aew.__file__))
    sha = sha256_file(binary)
    if sha != pinned_sha():
        raise ValueError("OpenCode binary does not match the Linux x64 pin in opencode/capabilities.py")
    commit = aew_revision()
    if not commit or commit.endswith("+dirty"):
        raise ValueError("the probe needs a clean Git checkout so the result names its exact commit")
    out.mkdir(mode=0o700)
    env = private_env(out / "catalog-private", harness="opencode")
    env.update(OPENCODE_DISABLE_PROJECT_CONFIG="1", OPENCODE_DISABLE_AUTOUPDATE="1")
    work = out / "catalog"
    work.mkdir(mode=0o700)
    if legs:
        # The harness child clears PYTHONPATH. Verify the package that this interpreter imports in that environment.
        child = subprocess.run([sys.executable, "-B", "-c", "import aew; print(aew.__file__)"], env=env, cwd=work,
                               stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False)
        if child.returncode:
            raise ValueError("the probe Python cannot import installed AEW in a private environment")
        verify_package(Path(child.stdout.decode("utf-8").strip()))
    version = pinned_version(run_binary(binary, env, work, "--version"))
    if sha != pinned_sha(version):
        raise ValueError("OpenCode version does not match the pinned binary digest")
    providers = catalog(binary, work, env)
    result = record(commit, version, sha, proof, providers, prove_catalog(providers))
    print(f"Verified Linux isolation and OpenCode {version}. Keyless catalog: {', '.join(providers)}", flush=True)
    result["complete"] = False
    document = out / "record.json"

    def save_record() -> None:
        pending = document.with_suffix(".tmp")
        pending.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        pending.replace(document)

    save_record()
    for leg in legs:
        from lead_probe import listchanged, session

        actions = {"lead": session.lead, "worker": session.worker, "listchanged": listchanged.run}
        print(f"Starting {leg} leg", flush=True)
        path = out / leg
        path.mkdir(mode=0o700)
        result["legs"][leg] = actions[leg](binary, path)
        save_record()
    result["complete"] = True
    save_record()
    lines = [f"E231 Lead probe at {commit}", f"OpenCode {version}, sha256 {sha}", "Network proof passed.",
             "Codex: not run. Windows: not run."]
    for leg, data in result["legs"].items():
        if leg == "listchanged":
            for case in data:
                lines.append(f"listChanged={case['declared']} {case['notification_order']}: "
                             f"next request {case['next_request_has_added_tool']}, "
                             f"next turn {case['next_turn_has_added_tool']}")
        else:
            lines.append(f"{leg} first request: {data['first_request']['raw_bytes']:,} bytes")
    (out / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--out", required=True, type=Path, help="a fresh output directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--leg", action="append", choices=LEGS)
    mode.add_argument("--catalog-only", action="store_true", help="capture the keyless catalog without model turns")
    mode.add_argument("--analyse", type=Path, metavar="CAPTURE", help="recompute the Lead results from saved bodies")
    parser.add_argument("--no-network", action="store_true", help="network isolation is always required")
    args = parser.parse_args(arguments)
    if args.analyse is None and args.binary is None:
        parser.error("--binary is required for a measurement")
    try:
        if args.analyse is not None:
            from lead_probe import measure as analysis

            analysis.reanalyse(args.analyse.resolve(), args.out.resolve())
            return 0
        if sys.platform == "win32":
            raise ValueError(HOLD)
        if sys.platform != "linux":
            raise ValueError("a verified Linux loopback-only namespace is required")
        if os.environ.get(REEXEC) != "1":
            unshare, ip = shutil.which("unshare"), shutil.which("ip")
            for name, executable in (("unshare", unshare), ("ip", ip)):
                if not executable:
                    raise ValueError(f"{name} not found. Install it or put it on PATH.")
            cmd = [unshare, "-rn", "/bin/sh", "-c", '"$1" link set lo up && shift && exec "$@"',
                   "lead-probe", ip, sys.executable, "-B", str(Path(__file__).resolve()), *arguments]
            code = subprocess.run(cmd, env={**os.environ, REEXEC: "1"}, check=False).returncode
            return code
        proof = network.prove()
        sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tests/helpers")]
        legs = [] if args.catalog_only else list(dict.fromkeys(args.leg or LEGS))
        measure(args.binary.resolve(strict=True), args.out.resolve(), legs, proof)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"lead probe: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
