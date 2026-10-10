"""F20.5: the frontend's production build in the package, its provenance, and static path resolution (design note
§4.13 R20, §4.14 R23; §5.4)."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from dashboard_contract import approval as load_approval
from dashboard_contract import base_contract, git_show, note_text, proposed

from aew.dashboard import contract as CT
from aew.dashboard import frontend as F
from aew.dashboard.server import CONDITIONAL_ROUTES, ROUTES

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "aew" / "dashboard" / "static"
# The commit agreed with the web developer and the operator for F20.5 (2026-10-05): never the newest by default.
AGREED_COMMIT = "4f0a710fa4831eefda248dd43cc2e144d1010189"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def build() -> dict:
    return json.loads((STATIC / "BUILD.json").read_text(encoding="utf-8"))


def built_files() -> set[str]:
    return {p.relative_to(STATIC).as_posix() for p in STATIC.rglob("*") if p.is_file()} - {"BUILD.json"}


# ---------------------------------------------------------------------------------------------- provenance

def test_build_json_binds_every_file_by_its_hash():
    record = build()
    assert record["schema"] == "aew/dashboard-build/v1"
    assert set(record["files"]) == built_files()  # nothing unrecorded, nothing missing
    for rel, digest in record["files"].items():
        assert hashlib.sha256((STATIC / rel).read_bytes()).hexdigest() == digest, rel


def test_build_json_names_the_agreed_commit_the_accepted_contract_and_the_pinned_builder():
    record = build()
    assert record["source"]["commit"] == AGREED_COMMIT
    assert re.fullmatch(r"[0-9a-f]{40}", record["source"]["tree"])
    assert re.fullmatch(r"[0-9a-f]{40}", record["source"]["web_tree"])
    assert record["contract"]["path"] == CT.CONTRACT_REL and re.fullmatch(r"[0-9a-f]{64}", record["contract"]["sha256"])
    pinned = (ROOT / "web/docs/how-to/pinned-web-builder.md").read_text(encoding="utf-8")
    assert record["builder"]["image"] in pinned and record["builder"]["image"].startswith("sha256:")
    assert record["builder"]["node"].startswith("v") and record["builder"]["npm"]
    assert set(record["inputs"]) == {"web/package.json", "web/package-lock.json"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", d) for d in record["inputs"].values())
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", record["built_at"])


def test_build_json_matches_the_commit_where_git_has_it():
    """The recorded tree and input digests are the commit's own (a shallow clone without the commit skips)."""
    record = build()
    got = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", f"{AGREED_COMMIT}^{{commit}}"],
                         capture_output=True, creationflags=NO_WINDOW)
    if got.returncode != 0:
        pytest.skip("the agreed commit is not in this clone")

    def show(spec: str) -> bytes:
        return subprocess.run(["git", "-C", str(ROOT), *spec.split()], check=True, capture_output=True,
                              creationflags=NO_WINDOW).stdout

    assert show(f"rev-parse {AGREED_COMMIT}^{{tree}}").decode().strip() == record["source"]["tree"]
    assert show(f"rev-parse {AGREED_COMMIT}:web").decode().strip() == record["source"]["web_tree"]
    for rel, digest in record["inputs"].items():
        assert hashlib.sha256(show(f"show {AGREED_COMMIT}:{rel}")).hexdigest() == digest, rel


def test_the_packaged_builds_contract_is_accepted_and_compatible_with_the_accepted_one():
    """The packaged build speaks the accepted contract or an accepted predecessor (a ``previous_reviews`` entry with
    ``"disposition": "ACCEPT"``): a rule, not a list, so neither the web developer's next minor version nor S3's
    re-import needs an edit here. The build's own contract, read from git at its source commit, must pass the
    compatibility check against the accepted one on every path of the build's contract that this server serves or
    serves conditionally; a path the build's contract lacks is exempt, since the build never requests it (change
    note §3.3; it also guards an import that ran before the shape it parses was served)."""
    record = build()
    approval = load_approval()
    assert record["contract"]["sha256"] in {r["sha256"] for r in CT.accepted_reviews(approval)}, (
        "the packaged build speaks a contract the approval record does not accept")
    raw = git_show(record["source"]["commit"], CT.CONTRACT_REL)
    assert hashlib.sha256(raw).hexdigest() == record["contract"]["sha256"]
    built = CT.Contract(raw=raw).document
    accepted = CT.Contract(ROOT / CT.CONTRACT_REL).document
    assert CT.compatibility(built, accepted, client_paths(built)) == []


def client_paths(client: dict) -> set[str]:
    """The paths a client's contract shares with what this server serves (conditional routes included, on or off)."""
    return set(client["paths"]) & (set(ROUTES) | CONDITIONAL_ROUTES)


def test_a_build_of_0_1_2_works_against_0_1_3_including_routes_it_does_not_know():
    base = base_contract()
    v013 = proposed(note_text(), base)
    serving = set(ROUTES) | {"/maps", "/maps/structural", "/maps/structural/{root}", "/maps/structural/{root}/inputs",
                             "/maps/diff"} | {"/history/search"}
    covered = set(base["paths"]) & serving  # /maps is absent from the build's contract: exempt
    assert "/maps" not in covered
    assert CT.compatibility(base, v013, covered) == []


def test_a_build_of_0_1_3_works_against_a_0_1_4_that_only_adds_paths():
    base = base_contract()
    v013 = proposed(note_text(), base)
    v014 = copy.deepcopy(v013)
    v014["info"]["version"] = "0.1.4"
    v014["paths"]["/later"] = {"get": {"responses": {"200": {"description": "x"}}}}
    serving = set(v013["paths"])  # S1 and S2 serve everything 0.1.3 adds
    assert CT.in_series("0.1.4")  # and no contract.py edit is needed to accept it
    assert CT.compatibility(v013, v014, set(v013["paths"]) & serving) == []


def test_a_build_of_0_1_3_fails_against_a_0_1_4_that_changes_a_served_history_search():
    """The early-import guard (change note §3.3): once ``/history/search`` is served, a build that parses another
    ``HistorySearch`` is refused, so S2 cannot serve a shape the packaged build would reject."""
    base = base_contract()
    v013 = proposed(note_text(), base)
    v014 = copy.deepcopy(v013)
    v014["components"]["schemas"]["HistorySearch"]["properties"]["ranked"] = {"type": "boolean"}
    serving = set(ROUTES) | {"/history/search"}
    problems = CT.compatibility(v013, v014, set(v013["paths"]) & serving)
    assert "#/components/schemas/HistorySearch changed" in problems
    assert CT.compatibility(v013, v014, set(v013["paths"]) & set(ROUTES)) == []  # while still pending: free


def test_a_build_fails_against_a_contract_that_changes_an_existing_0_1_2_shape():
    base = base_contract()
    changed = copy.deepcopy(proposed(note_text(), base))
    changed["components"]["schemas"]["Work"]["properties"]["extra"] = {"type": "string"}
    assert CT.compatibility(base, changed, client_paths(base)) != []


def test_index_html_references_only_files_of_the_build():
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="([^"]+)"', index)
    assert refs, "index.html references its bundle"
    for ref in refs:
        assert ref.startswith("/") and not ref.startswith("//"), ref  # same origin, absolute path
        assert ref[1:] in built_files(), ref


def test_the_build_contains_no_demo_material():
    """The strings the frontend's own production check forbids (``web/scripts/check-production.mjs``), read from
    that script so the two never drift."""
    script = (ROOT / "web/scripts/check-production.mjs").read_text(encoding="utf-8")
    patterns = re.findall(r"/((?:[^/\n\\]|\\.)+)/\.test\(", script)
    assert len(patterns) >= 4, patterns
    for rel in built_files():
        text = (STATIC / rel).read_text(encoding="utf-8")
        for pattern in patterns:
            assert not re.search(pattern.replace("\\/", "/"), text), (rel, pattern)
    assert "mockServiceWorker" not in "".join(built_files())


def test_package_data_ships_every_file_of_the_build():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    globs = data["tool"]["setuptools"]["package-data"]["aew.dashboard"]
    shipped = {p.relative_to(STATIC.parent).as_posix() for g in globs for p in STATIC.parent.glob(g) if p.is_file()}
    assert shipped == {f"static/{rel}" for rel in built_files() | {"BUILD.json"}}


def test_the_packaged_root_is_the_committed_build():
    assert F.packaged_root() == STATIC
    assert F.build_record(STATIC) == build()


# ---------------------------------------------------------------------------------------------- resolution

@pytest.mark.parametrize("path", ["/", "/work", "/work/T-0012", "/history/T-0001/annotations", "/runs/INV-0001",
                                  "/session-help"])
def test_a_deep_link_is_the_spa_fallback(path):
    asset = F.resolve(STATIC, path)
    assert asset is not None and asset.path == STATIC / "index.html"
    assert asset.content_type.startswith("text/html") and asset.cache_control == "no-store"


def test_files_resolve_with_their_type_and_cache_policy():
    js = next(r for r in built_files() if r.endswith(".js"))
    asset = F.resolve(STATIC, "/" + js)
    assert asset is not None and asset.content_type.startswith("text/javascript")
    assert asset.cache_control == "max-age=31536000, immutable"  # content-hashed names
    icon = F.resolve(STATIC, "/favicon.svg")
    assert icon is not None and icon.content_type == "image/svg+xml" and icon.cache_control == "no-store"
    index = F.resolve(STATIC, "/index.html")
    assert index is not None and index.cache_control == "no-store"


@pytest.mark.parametrize("path", ["/mockServiceWorker.js", "/BUILD.json", "/nope.js", "/assets/nope.js",
                                  "/assets/index", "/favicon.exe", "/static/index.html", "/x.php"])
def test_unknown_files_and_never_served_files_are_404(path):
    assert F.resolve(STATIC, path) is None


@pytest.mark.parametrize("path", ["/..", "/../pyproject.toml", "/assets/../index.html", "/%2e%2e/x.js",
                                  "/assets/%2e%2e/%2e%2e/frontend.py", "/a%2Fb.js", "/a%2fb", "/a%5Cb.js",
                                  "/a\\b.js", "/./index.html", "//index.html", "/assets//x.js", "/a%00.js",
                                  "/%ff.js", "relative.js", "/assets/"])
def test_traversal_and_encoded_separators_are_refused(path):
    with pytest.raises(F.BadPath):
        F.resolve(STATIC, path)


def test_a_link_out_of_the_root_is_not_served(tmp_path):
    root = tmp_path / "build"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.js").write_text("secret", encoding="utf-8")
    try:
        (root / "assets" / "out").symlink_to(outside, target_is_directory=True)
    except OSError:  # Windows without the link privilege: a directory junction needs none
        import _winapi  # type: ignore[import-not-found]

        _winapi.CreateJunction(str(outside), str(root / "assets" / "out"))
    assert (root / "assets" / "out" / "secret.js").is_file()  # the link works ...
    assert F.resolve(root, "/assets/out/secret.js") is None  # ... and still serves nothing outside the root


# ---------------------------------------------------------------------------------------------- the import tool

def _import_tool():
    spec = importlib.util.spec_from_file_location("import_build", ROOT / "tools/dashboard/import_build.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<script src="/assets/a-1.js"></script>', encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (dist / "assets" / "a-1.js").write_text("console.log(1)", encoding="utf-8")
    return dist


@pytest.mark.parametrize("extra", ["mockServiceWorker.js", "notes.txt", "assets/sub/x.js", "other/x.js"])
def test_the_import_refuses_anything_but_the_build(tmp_path, extra):
    tool = _import_tool()
    dist = _dist(tmp_path)
    (dist / extra).parent.mkdir(parents=True, exist_ok=True)
    (dist / extra).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        tool.build_files(dist)


def test_the_import_refuses_a_dist_without_index(tmp_path):
    tool = _import_tool()
    dist = _dist(tmp_path)
    (dist / "index.html").unlink()
    with pytest.raises(SystemExit):
        tool.build_files(dist)


def test_the_import_writes_the_build_and_its_record(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git is required")
    tool = _import_tool()
    monkeypatch.setattr(tool, "STATIC", tmp_path / "static")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
                          creationflags=NO_WINDOW).stdout.strip()
    image = "sha256:" + "a" * 64
    dist = _dist(tmp_path)
    assert tool.main([str(dist), "--source-commit", head, "--builder-image", image, "--node", "v22.0.0",
                      "--npm", "10.0.0", "--built-at", "2026-10-06T00:00:00Z"]) == 0
    record = json.loads((tmp_path / "static" / "BUILD.json").read_text(encoding="utf-8"))
    assert record["source"]["commit"] == head and record["builder"]["image"] == image
    assert set(record["files"]) == {"index.html", "favicon.svg", "assets/a-1.js"}
    assert record["files"]["assets/a-1.js"] == hashlib.sha256(b"console.log(1)").hexdigest()
    with pytest.raises(SystemExit):
        tool.main([str(dist), "--source-commit", head, "--builder-image", "latest", "--node", "v22",
                   "--npm", "10", "--built-at", "2026-10-06T00:00:00Z"])  # a mutable image name is refused


def test_build_json_matches_the_web_build_agreement():
    """``web/docs/reference/f20-production-baseline.md`` is the operator-approved baseline (web agent, 2026-10-05):
    every identity it records is the one ``BUILD.json`` binds, so a rebuild from another commit, toolchain or
    lockfile fails here until a new baseline is agreed."""
    agreement = (ROOT / "web/docs/reference/f20-production-baseline.md").read_text(encoding="utf-8")
    table = dict(re.findall(r"^\| ([^|]+?) \| `?([^|`]+?)`? \|$", agreement, re.M))
    record = build()
    assert table["Frontend source commit"] == record["source"]["commit"] == AGREED_COMMIT
    assert table["Repository tree"] == record["source"]["tree"]
    assert table["Frontend subtree"] == record["source"]["web_tree"]
    assert table["Contract SHA-256 at that commit"] == record["contract"]["sha256"]
    assert record["inputs"]["web/package-lock.json"] in agreement and record["inputs"]["web/package.json"] in agreement
    assert table["Pinned builder image"] == record["builder"]["image"]
    assert table["Toolchain"] == f"Node {record['builder']['node'].lstrip('v')} / npm {record['builder']['npm']}"


# ---------------------------------------------------------------------------------------------- the request log

def test_the_request_log_never_blocks_a_request_on_a_stalled_terminal():
    """``serve`` logs to its terminal; a terminal that stops reading (Ctrl-S, a suspended emulator) must stall
    only the log's writer: logging returns at once, lines beyond the queue are dropped, and closing never hangs."""
    import logging
    import threading
    import time

    from aew.dashboard.server import RequestLog

    class Stalled:
        def __init__(self) -> None:
            self.release = threading.Event()
            self.lines: list[str] = []

        def write(self, text: str) -> None:
            self.release.wait()
            self.lines.append(text)

        def flush(self) -> None:
            pass

    stream = Stalled()
    handler = RequestLog(stream, capacity=8)  # type: ignore[arg-type]
    logger = logging.getLogger("aew.dashboard.test-request-log")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    requests = threading.Thread(target=lambda: [logger.info("GET /api/v1/project 200 %dms", n) for n in range(200)],
                                daemon=True)
    try:
        requests.start()
        requests.join(5.0)
        assert not requests.is_alive(), "logging blocked on the stalled terminal"
        assert handler.dropped >= 200 - 8 - 1
        started = time.monotonic()
        handler.close()
        assert time.monotonic() - started < 3.0  # shutdown does not wait for the terminal either
    finally:
        stream.release.set()
        logger.removeHandler(handler)


def test_dropped_request_log_lines_are_reported_once_the_writer_catches_up():
    """A gap in the request log is never silent: the next line written says how many were dropped (review of
    PR #90, finding 7)."""
    import logging
    import re
    import threading
    import time

    from aew.dashboard.server import RequestLog

    class Gated:
        def __init__(self) -> None:
            self.release = threading.Event()
            self.text = ""

        def write(self, text: str) -> None:
            self.release.wait()
            self.text += text

        def flush(self) -> None:
            pass

    stream = Gated()
    handler = RequestLog(stream, capacity=2)  # type: ignore[arg-type]
    logger = logging.getLogger("aew.dashboard.test-dropped")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        for n in range(20):
            logger.info("line %d", n)
        assert handler.dropped >= 20 - 2 - 1
        stream.release.set()
        deadline = time.monotonic() + 5
        while not handler._lines.empty() and time.monotonic() < deadline:  # noqa: SLF001 (the writer caught up)
            time.sleep(0.01)
        logger.info("after")
        handler.close()
        reported = sum(int(n) for n in re.findall(r"(\d+) request log line\(s\) dropped", stream.text))
        assert reported == handler.dropped and "after" in stream.text, stream.text
    finally:
        stream.release.set()
        logger.removeHandler(handler)


def test_the_spa_index_is_held_to_the_same_containment(tmp_path):
    """A build whose ``index.html`` is a link out of the root serves nothing for ``/`` or a deep link, as a
    direct request for it does not (review of PR #90)."""
    root = tmp_path / "build"
    root.mkdir()
    outside = tmp_path / "outside.html"
    outside.write_text("<p>outside</p>", encoding="utf-8")
    try:
        (root / "index.html").symlink_to(outside)
    except OSError:
        pytest.skip("this platform does not let the test create a file link (Linux CI runs it)")
    for path in ("/", "/work/T-0001", "/index.html"):
        assert F.resolve(root, path) is None, path


def test_the_spa_index_must_be_a_regular_file(tmp_path):
    root = tmp_path / "build"
    (root / "index.html").mkdir(parents=True)  # a directory where the index should be
    assert F.resolve(root, "/") is None and F.resolve(root, "/work") is None


@pytest.mark.parametrize("path", ["/build.json", "/Build.Json", "/BUILD.JSON", "/mockserviceworker.js",
                                  "/MOCKSERVICEWORKER.JS", "/assets/BUILD.json"])
def test_withheld_names_are_withheld_in_any_casing(path, tmp_path):
    assert F.resolve(STATIC, path) is None
    root = tmp_path / "custom"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("x", encoding="utf-8")
    (root / "mockServiceWorker.js").write_text("x", encoding="utf-8")
    (root / "assets" / "BUILD.json").write_text("{}", encoding="utf-8")
    assert F.resolve(root, path) is None


def test_the_bounds_the_design_records_are_the_servers():
    """PR #90 review, finding 6: the connection bound, the busy answer, the head deadline and the log queue are written
    down where R23 is, with the values the server uses. In the fast lane, which every CI tier runs: a docs-only change
    to R23 or the ledger must meet it (CI redesign P1's guard)."""
    from aew.dashboard import server as SV

    note = (ROOT / "docs/design/proposals/dashboard-main-line-api-design-v0.1.md").read_text(encoding="utf-8")
    ledger = (ROOT / "docs/design/requirements-ledger.yaml").read_text(encoding="utf-8")
    for text in (note, ledger):
        assert f"{SV.MAX_CONNECTIONS} connections" in text
        assert f"{SV.HEAD_DEADLINE_S:.0f} s" in text and f"{SV.LOG_QUEUE} lines" in text

