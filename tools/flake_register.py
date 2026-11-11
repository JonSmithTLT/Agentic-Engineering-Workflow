"""Validate the flake register and report its trailing seven-day queue."""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile
from zlib import error as CompressionError

import yaml

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
REGISTER = "tests/flake-register.yaml"
REGISTER_PATH = TESTS / "flake-register.yaml"
SCHEMA = "aew/flake-register/v1"
PLATFORMS = {"linux", "windows"}
WINDOW = timedelta(days=7)
THRESHOLD = 3
CHECK_BATCH_SIZE = 25
CHECK_CONCURRENCY = 4
CHECK_QUERY = """query($ids: [ID!]!) {
  nodes(ids: $ids) {
    ... on WorkflowRun {
      id
      checkSuite {
        cancelled: checkRuns(first: 100, filterBy: {checkType: ALL, conclusions: [CANCELLED, TIMED_OUT]}) {
          ...Checks
        }
        active: checkRuns(first: 100, filterBy: {checkType: ALL, statuses: [IN_PROGRESS]}) { ...Checks }
      }
    }
  }
}
fragment Checks on CheckRunConnection {
  pageInfo { hasNextPage }
  nodes { id name databaseId startedAt conclusion status }
}"""
CHECK_DETAILS = """query($ids: [ID!]!) {
  nodes(ids: $ids) {
    ... on CheckRun {
      id
      steps(first: 40) { pageInfo { hasNextPage } nodes { name startedAt } }
      annotations(first: 12) { pageInfo { hasNextPage } nodes { message } }
    }
  }
}"""
IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
INDEX_ARTIFACT = "flake-sighting-index"
INDEX_MEMBER = "sightings.json"
MAX_INDEX_BYTES = 1024 * 1024
TEST_NAME = re.compile(r"test_\w+\Z")
NO_RESPONSE = re.compile(r"stopped hearing from|not responding|has exceeded the maximum execution time", re.I)
PYTEST_STEP = re.compile(
    r"pytest|(?:fast|serial) lane|racing writers|randomized crash iterations|deadline plants", re.I,
)


class InvalidRegister(ValueError):
    """Malformed evidence or a flake register that cannot be used."""


class RegisterLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        pairs = self.construct_pairs(node, deep=deep)
        result = {}
        for key, value in pairs:
            if not isinstance(key, str) or key in result:
                raise InvalidRegister(f"invalid or duplicate mapping key: {key!r}")
            result[key] = value
        return result


class RegisterDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def read_source(path: str) -> str | None:
    file = TESTS / path.removeprefix("tests/")
    return file.read_text(encoding="utf-8") if file.is_file() else None


@cache
def lane_policy() -> tuple[tuple[str, ...], str, str]:
    helpers = str(ROOT / "tests" / "helpers")
    if helpers not in sys.path:
        sys.path.insert(0, helpers)
    from lanes import LANES
    from vertical.ledger import VERTICAL_MODE, VERTICAL_MODES

    return LANES, VERTICAL_MODE, VERTICAL_MODES[0]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise InvalidRegister("a sighting needs an ISO timestamp with a timezone")
    try:
        when = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidRegister(f"invalid timestamp {value!r}") from exc
    if when.utcoffset() is None:
        raise InvalidRegister(f"timestamp lacks a timezone: {value!r}")
    return when.astimezone(UTC)


def _test_exists(node: Any, source: Callable[[str], str | None]) -> bool:
    if not isinstance(node, str) or "::" not in node:
        return False
    file, *parts = node.split("::")
    path = PurePosixPath(file)
    if (path.as_posix() != file or not file.startswith("tests/") or ".." in path.parts or "\\" in file
            or path.suffix != ".py" or not path.name.startswith("test_")):
        return False
    name = parts[-1].split("[", 1)[0]
    if not TEST_NAME.fullmatch(name) or ("[" in parts[-1] and not parts[-1].endswith("]")):
        return False
    contents = source(file)
    if contents is None:
        return False
    try:
        body = ast.parse(contents).body
    except SyntaxError:
        return False
    for cls in parts[:-1]:
        match = next((statement for statement in body if isinstance(statement, ast.ClassDef)
                      and statement.name == cls), None)
        if match is None:
            return False
        body = match.body
    return any(isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)) and statement.name == name
               for statement in body)


def _evidence_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return row["run"], row["job"], row.get("observation", "")


def _validate_evidence(rows: Any, *, source: Callable[[str], str | None] | None = None) -> None:
    if not isinstance(rows, list) or not rows:
        raise InvalidRegister("at least one item of evidence is required")
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not {"run", "job", "at"} <= row.keys()
                or set(row) - {"run", "job", "at", "observation", "note", "nodes", "kind"}):
            raise InvalidRegister("evidence needs run, job and at")
        if any(type(row[key]) is not int or row[key] <= 0 for key in ("run", "job")):
            raise InvalidRegister("run and job IDs must be positive integers")
        _time(row["at"])
        if row.get("kind", "sighting") not in ("sighting", "diagnostic"):
            raise InvalidRegister("unknown evidence kind")
        if "observation" in row and not _nonempty(row["observation"]):
            raise InvalidRegister("empty observation identity")
        if "note" in row and not _nonempty(row["note"]):
            raise InvalidRegister("empty evidence note")
        if "nodes" in row:
            if source is None or not isinstance(row["nodes"], list) or not row["nodes"]:
                raise InvalidRegister("only session evidence can list observed test nodes")
            if any(not _test_exists(node, source) for node in row["nodes"]):
                raise InvalidRegister("session evidence test node does not exist")
        key = _evidence_key(row)
        if key in seen:
            raise InvalidRegister(f"duplicate evidence {key}")
        seen.add(key)


def _validate_entry(entry: dict[str, Any], source: Callable[[str], str | None]) -> None:
    lanes, vertical_mode, shadow = lane_policy()
    scope = entry.get("scope")
    lane = entry.get("lane")
    platforms = entry.get("platforms")
    required = {"id", "scope", "lane", "platforms", "status", "class", "cause", "owner", "evidence"}
    extra = {"row", "planned_fix", "closure"} | ({"test"} if scope == "test" else set())
    if not required <= entry.keys() or set(entry) - (required | extra):
        raise InvalidRegister("missing or unknown entry fields")
    if scope not in ("test", "session") or entry["status"] not in ("open", "closed"):
        raise InvalidRegister("invalid scope or status")
    if (not isinstance(platforms, list) or not platforms or any(p not in ("linux", "windows") for p in platforms)
            or len(platforms) != len(set(platforms))):
        raise InvalidRegister(f"platforms must be distinct and drawn from {sorted(PLATFORMS)}")
    if not all(_nonempty(entry[key]) for key in ("owner", "class", "cause")):
        raise InvalidRegister("owner, class and suspected cause are required")
    if any(key in entry and not _nonempty(entry[key]) for key in ("row", "planned_fix")):
        raise InvalidRegister("row and planned fix must be named when supplied")
    if not isinstance(lane, str) or not lane.strip() or (scope == "test" and lane not in lanes):
        raise InvalidRegister("invalid test lane or session lane pattern")
    if scope == "session" and not any(fnmatchcase(known, lane) for known in lanes):
        raise InvalidRegister("session lane pattern matches no lane")
    if vertical_mode == shadow and fnmatchcase("vertical", lane):
        raise InvalidRegister("vertical is in shadow mode")
    if scope == "test" and not _test_exists(entry.get("test"), source):
        raise InvalidRegister("test node does not exist")
    _validate_evidence(entry["evidence"], source=source if scope == "session" else None)
    if entry["status"] == "open" and not any(row.get("kind", "sighting") == "sighting" for row in entry["evidence"]):
        raise InvalidRegister("an open entry needs sighting evidence")
    if entry["status"] == "open" and "closure" in entry:
        raise InvalidRegister("open entry has a closure")
    if entry["status"] == "closed":
        closure = entry.get("closure")
        if (not isinstance(closure, dict) or set(closure) != {"cause", "test", "proof", "pr"}
                or not _nonempty(closure["cause"]) or type(closure["pr"]) is not int or closure["pr"] <= 0
                or closure["proof"] not in ("event", "fault injection", "fixed order")
                or not _test_exists(closure["test"], source)):
            raise InvalidRegister("closure needs a cause, PR and existing deterministic test "
                                  "by event, fault injection or fixed order")


def load_register(text: str, source: Callable[[str], str | None] = read_source) -> dict[str, Any]:
    source = cache(source)
    try:
        doc = yaml.load(text, Loader=RegisterLoader)  # noqa: S506 - SafeLoader with duplicate-key checks.
    except yaml.YAMLError as exc:
        raise InvalidRegister(f"invalid YAML: {exc}") from exc
    if (not isinstance(doc, dict) or set(doc) != {"schema", "entries", "census"} or doc["schema"] != SCHEMA
            or not isinstance(doc["entries"], list) or not doc["entries"] or not isinstance(doc["census"], list)):
        raise InvalidRegister(f"expected a nonempty {SCHEMA} register and a census list")
    ids = set()
    for entry in doc["entries"]:
        ident = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(ident, str) or not IDENTIFIER.fullmatch(ident) or ident in ids:
            raise InvalidRegister(f"invalid or duplicate entry ID: {ident!r}")
        try:
            _validate_entry(entry, source)
        except InvalidRegister as exc:
            raise InvalidRegister(f"{ident}: {exc}") from exc
        ids.add(ident)
    for row in doc["census"]:
        if (not isinstance(row, dict) or set(row) != {"test", "platform", "lane", "evidence"}
                or row["platform"] not in ("linux", "windows") or row["lane"] not in lane_policy()[0]
                or not _test_exists(row["test"], source)):
            raise InvalidRegister("invalid census node, platform or lane")
        _validate_evidence(row["evidence"])
    return doc


def validate_history(base: dict[str, Any], current: dict[str, Any]) -> None:
    entries = {entry["id"]: entry for entry in current["entries"]}
    for old in base["entries"]:
        ident = old["id"]
        if ident not in entries:
            raise InvalidRegister(f"{ident}: base entry must be retained")
        new = entries[ident]
        evidence = {_evidence_key(row): row for row in new["evidence"]}
        if any(evidence.get(_evidence_key(row)) != row for row in old["evidence"]):
            raise InvalidRegister(f"{ident}: base evidence is append-only")
        if "closure" in old and new.get("closure") != old["closure"]:
            raise InvalidRegister(f"{ident}: base closure must be retained")


def check_base(base_ref: str, current: dict[str, Any]) -> None:
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True,
                              encoding="utf-8", timeout=30).stdout

    base = git("rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").strip()
    tree = git("ls-tree", base, "--", REGISTER)
    if not tree:
        return  # The register is being introduced.
    if not tree.startswith("100644 blob "):
        raise InvalidRegister("base register must be a regular file")

    def source(path: str) -> str | None:
        try:
            return git("show", f"{base}:{path}")
        except subprocess.CalledProcessError:
            return None

    validate_history(load_register(git("show", f"{base}:{REGISTER}"), source), current)


def index_sightings(data: bytes, run: int) -> Iterable[tuple[str, dict[str, Any]]]:
    if len(data) > MAX_INDEX_BYTES:
        raise InvalidRegister("oversized flake sighting index archive")
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            if archive.namelist() != [INDEX_MEMBER] or archive.getinfo(INDEX_MEMBER).file_size > MAX_INDEX_BYTES:
                raise InvalidRegister("invalid flake sighting index member")
            rows = json.loads(archive.read(INDEX_MEMBER))
    except (BadZipFile, CompressionError, EOFError, RuntimeError, NotImplementedError) as exc:
        raise InvalidRegister("invalid flake sighting index archive") from exc
    if not isinstance(rows, list):
        raise InvalidRegister("flake sighting index must contain a list")
    for row in rows:
        if (not isinstance(row, dict) or not {"entry", "job", "at"} <= row.keys()
                or row.keys() - {"entry", "job", "at", "observation"}
                or not isinstance(row["entry"], str) or not IDENTIFIER.fullmatch(row["entry"])):
            raise InvalidRegister("invalid flake sighting index row")
        evidence = {key: value for key, value in row.items() if key != "entry"} | {"run": run}
        _validate_evidence([evidence])
        yield row["entry"], evidence


def _started_pytest(steps: list[dict[str, Any]]) -> bool:
    return not steps or any(
        step.get("started_at") and (PYTEST_STEP.search(step["name"]) or "--lane " in step["name"])
        and not step["name"].startswith("The job's deadline") for step in steps)


def session_problem(run: dict[str, Any], job: dict[str, Any], annotations: list[dict[str, Any]], now: datetime) -> bool:
    if not _started_pytest(job.get("steps") or []):
        return False
    if any(NO_RESPONSE.search(annotation["message"]) for annotation in annotations):
        return True
    return (run["conclusion"] == "cancelled" and job["status"] == "in_progress"
            and now - _time(run["updated_at"]) >= timedelta(minutes=5))


def _platform(name: str) -> str | None:
    return next((platform for platform, runner in (("windows", "windows-"), ("linux", "ubuntu-"))
                 if runner in name), None)


def _lane(name: str) -> str:
    lane = re.split(r" \d+/\d+| \(", name, maxsplit=1)[0]
    # The nightly full-suite shards also exercise regression tests.
    return "regression" if lane == "full suite" else lane


def _matches_session(entry: dict[str, Any], name: str) -> bool:
    return _platform(name) in entry["platforms"] and fnmatchcase(_lane(name), entry["lane"])


def _candidate_run(run: dict[str, Any]) -> bool:
    return run["conclusion"] in ("cancelled", "failure", "timed_out") or run.get("run_attempt", 1) > 1


def session_sightings(doc: dict[str, Any], runs: Iterable[dict[str, Any]],
                      jobs: Callable[[dict[str, Any]], Iterable[dict[str, Any]]],
                      annotations: Callable[[int], list[dict[str, Any]]],
                      now: datetime) -> Iterable[tuple[str, dict[str, Any]]]:
    entries = [entry for entry in doc["entries"] if entry["scope"] == "session" and entry["status"] == "open"]
    for run in runs:
        if not _candidate_run(run):
            continue
        for job in jobs(run):
            cancelled = job["conclusion"] in ("cancelled", "timed_out")
            if not cancelled and job["status"] != "in_progress":
                continue
            matched = [entry for entry in entries if _matches_session(entry, job["name"])]
            if not matched or not job.get("started_at") or not _started_pytest(job.get("steps") or []):
                continue
            notes = annotations(job["id"]) if cancelled else []
            if session_problem(run, job, notes, now):
                for entry in matched:
                    yield entry["id"], {"run": run["id"], "job": job["id"], "at": job["started_at"]}


def queue(doc: dict[str, Any], recent: Iterable[tuple[str, dict[str, Any]]],
          now: datetime) -> list[tuple[str, int, bool]]:
    seen = {entry["id"]: set() for entry in doc["entries"] if entry["status"] == "open"}

    def add(ident: str, row: dict[str, Any]) -> None:
        if ident in seen and row.get("kind", "sighting") == "sighting" and now - WINDOW <= _time(row["at"]) <= now:
            seen[ident].add(_evidence_key(row))

    for entry in doc["entries"]:
        for row in entry["evidence"]:
            add(entry["id"], row)
    for ident, row in recent:
        add(ident, row)
    counts = {ident: len(keys) for ident, keys in seen.items()}
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [(ident, count, count >= THRESHOLD) for ident, count in ordered]


def _gh_read(*args: str) -> bytes:
    result = subprocess.run(["gh", "api", *args],
                            check=True, capture_output=True, timeout=45,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return result.stdout


def _gh_json(*args: str) -> Any:
    return json.loads(_gh_read(*args))


def _api(repo: str, endpoint: str, *flags: str) -> Any:
    return _gh_json(*flags, f"repos/{repo}/{endpoint}")


def _pages(repo: str, endpoint: str, key: str | None = None) -> Iterable[dict[str, Any]]:
    for page in _api(repo, endpoint, "--paginate", "--slurp"):
        yield from page[key] if key else page


def _own_ci_run(repo: str, run: dict[str, Any]) -> bool:
    return (run.get("path") == ".github/workflows/ci.yml" and run.get("head_branch") == "main"
            and run.get("event") in {"push", "workflow_dispatch"}
            and all(((run.get(key) or {}).get("full_name") or "").casefold() == repo.casefold()
                    for key in ("repository", "head_repository")))


def _index_warning(message: str) -> None:
    print(message, file=sys.stderr)


def recent_index_sightings(
    repo: str, cutoff: datetime, warn: Callable[[str], None] = _index_warning,
) -> Iterable[tuple[str, dict[str, Any]]]:
    # GitHub filters exact names, and pages can contain out-of-order timestamps.
    trusted: dict[int, bool] = {}
    for artifact in _pages(repo, f"actions/artifacts?per_page=100&name={INDEX_ARTIFACT}", "artifacts"):
        if artifact["expired"] or _time(artifact["created_at"]) < cutoff:
            continue
        run = (artifact.get("workflow_run") or {}).get("id")
        artifact_id = artifact["id"]
        if type(run) is not int or run < 1 or type(artifact_id) is not int or artifact_id < 1:
            warn("Skipped a flake sighting index with invalid artifact or run metadata.")
            continue
        if run not in trusted:
            trusted[run] = _own_ci_run(repo, _api(repo, f"actions/runs/{run}"))
        if not trusted[run]:
            continue
        try:
            if not 0 < artifact["size_in_bytes"] <= MAX_INDEX_BYTES:
                raise InvalidRegister("invalid flake sighting index size")
            data = _gh_read(f"repos/{repo}/actions/artifacts/{artifact_id}/zip")
            rows = list(index_sightings(data, run))
        except (ValueError, KeyError, TypeError):
            warn(f"Skipped malformed flake sighting index {artifact_id} from run {run}.")
            continue
        yield from rows


def _check_nodes(query: str, ids: list[str]) -> dict[str, Any]:
    def fetch(batch: list[str]) -> list[dict[str, Any]]:
        fields = [arg for ident in batch for arg in ("-f", f"ids[]={ident}")]
        response = _gh_json("graphql", "-f", f"query={query}", *fields)
        return response["data"]["nodes"]

    batches = [ids[offset:offset + CHECK_BATCH_SIZE] for offset in range(0, len(ids), CHECK_BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=CHECK_CONCURRENCY) as pool:
        results = {node["id"]: node for batch in pool.map(fetch, batches) for node in batch if node}
    if results.keys() != set(ids):
        raise InvalidRegister("some workflow check data is unavailable")
    return results


def _checks_to_jobs(
    repo: str, run: dict[str, Any], suite: dict[str, Any], names: Callable[[str], bool],
) -> Iterable[dict[str, Any]]:
    connections = [suite["cancelled"]]
    if run["conclusion"] == "cancelled":
        connections.append(suite["active"])
    if any(conn["pageInfo"]["hasNextPage"] for conn in connections):
        yield from _pages(repo, f"actions/runs/{run['id']}/jobs?filter=all&per_page=100", "jobs")
        return
    for conn in connections:
        for check in conn["nodes"]:
            if check["startedAt"] and names(check["name"]):
                yield {"id": check["databaseId"], "name": check["name"], "started_at": check["startedAt"],
                       "conclusion": (check["conclusion"] or "").lower(), "status": check["status"].lower(),
                       "check_id": check["id"]}


def _apply_check_details(repo: str, job: dict[str, Any], detail: dict[str, Any]) -> None:
    steps, notes = detail["steps"], detail["annotations"]
    if steps and steps["pageInfo"]["hasNextPage"]:
        job["steps"] = _api(repo, f"actions/jobs/{job['id']}")["steps"]
    else:
        job["steps"] = [{"name": step["name"], "started_at": step["startedAt"]}
                        for step in (steps or {}).get("nodes", [])]
    if notes is not None and not notes["pageInfo"]["hasNextPage"]:
        job["annotations"] = notes["nodes"]


def _github_sessions(
    doc: dict[str, Any], repo: str, runs: list[dict[str, Any]], now: datetime,
) -> Iterable[tuple[str, dict[str, Any]]]:
    open_sessions = [entry for entry in doc["entries"] if entry["status"] == "open" and entry["scope"] == "session"]

    def matching(name: str) -> bool:
        return any(_matches_session(entry, name) for entry in open_sessions)

    checks = _check_nodes(CHECK_QUERY, [run["node_id"] for run in runs])
    jobs_by_run = {run["id"]: list(_checks_to_jobs(repo, run, checks[run["node_id"]]["checkSuite"], matching))
                   for run in runs}
    check_jobs = [job for jobs in jobs_by_run.values() for job in jobs if "check_id" in job]
    details = _check_nodes(CHECK_DETAILS, [job["check_id"] for job in check_jobs])
    for job in check_jobs:
        _apply_check_details(repo, job, details[job["check_id"]])
    notes = {job["id"]: job["annotations"] for job in check_jobs if "annotations" in job}

    def annotations(job: int) -> list[dict[str, Any]]:
        if job in notes:
            return notes[job]
        return list(_pages(repo, f"check-runs/{job}/annotations?per_page=100"))

    yield from session_sightings(doc, runs, lambda run: jobs_by_run[run["id"]], annotations, now)


def _workflow_runs(repo: str, workflow: str, now: datetime) -> list[dict[str, Any]]:
    start = (now - WINDOW).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # A fixed upper bound keeps newly created runs from shifting the remaining pages.
    endpoint = f"actions/workflows/{workflow}/runs?created={quote(f'{start}..{end}')}&per_page=100"
    pages = _api(repo, endpoint, "--paginate", "--slurp")
    runs = {run["id"]: run for page in pages for run in page["workflow_runs"]}
    expected = max((page["total_count"] for page in pages), default=0)
    # GitHub caps filtered searches at 1,000. At the cap it may also cap total_count.
    if not pages or len(runs) < expected or len(runs) >= 1000:
        raise InvalidRegister(
            f"incomplete {workflow} run listing ({len(runs)} of {expected}); seven-day coverage unverified"
        )
    return list(runs.values())


def github_sightings(
    doc: dict[str, Any], repo: str, now: datetime, warn: Callable[[str], None] = _index_warning,
) -> Iterable[tuple[str, dict[str, Any]]]:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or any(part in {".", ".."} for part in repo.split("/")):
        raise InvalidRegister("expected a GitHub repository in owner/name form")
    yield from recent_index_sightings(repo, now - WINDOW, warn)
    for workflow in ("ci.yml", "nightly.yml"):
        runs = _workflow_runs(repo, workflow, now)
        yield from _github_sessions(doc, repo, [run for run in runs if _candidate_run(run)], now)


def record(doc: dict[str, Any], recent: Iterable[tuple[str, dict[str, Any]]], now: datetime) -> int:
    opened = {entry["id"]: entry["evidence"] for entry in doc["entries"] if entry["status"] == "open"}
    keys = {ident: {_evidence_key(row) for row in evidence} for ident, evidence in opened.items()}
    added = 0
    for ident, row in sorted(recent, key=lambda pair: (_time(pair[1]["at"]), pair[0], _evidence_key(pair[1]))):
        if ident not in opened or not now - WINDOW <= _time(row["at"]) <= now:
            continue
        key = _evidence_key(row)
        if key not in keys[ident]:
            opened[ident].append(row)
            keys[ident].add(key)
            added += 1
    return added


def _save(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                     delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(text)
            stream.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "queue", "record"))
    parser.add_argument("--repo", help="read recent GitHub sightings for this repository")
    parser.add_argument("--base", help="compare a checked register with this Git commit")
    args = parser.parse_args(argv)
    try:
        path = REGISTER_PATH
        doc = load_register(path.read_text(encoding="utf-8"))
        if args.command == "check":
            if args.base is not None:
                check_base(args.base, doc)
            print(f"{REGISTER}: {len(doc['entries'])} entries checked")
        elif args.command == "queue":
            now = datetime.now(UTC)
            warnings: list[str] = []
            recent = github_sightings(doc, args.repo, now, warnings.append) if args.repo else ()
            rows = queue(doc, recent, now)
            print("## Flake queue · last seven days\n")
            for ident, count, repeated in rows:
                print(f"- `{ident}`: {count}" + (" **repeat offender**" if repeated else ""))
            for warning in warnings:
                print(f"\n{warning}")
        else:
            if not args.repo:
                parser.error("record requires --repo")
            now = datetime.now(UTC)
            count = record(doc, github_sightings(doc, args.repo, now), now)
            if count:
                text = yaml.dump(doc, Dumper=RegisterDumper, sort_keys=False, allow_unicode=True, width=120)
                load_register(text)
                _save(path, text)
            print(f"{count} new sightings recorded")
    except (OSError, ValueError, subprocess.SubprocessError, KeyError) as exc:
        print(f"flake register: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
