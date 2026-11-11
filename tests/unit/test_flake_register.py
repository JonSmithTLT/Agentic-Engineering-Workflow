"""Flake register validation, evidence selection and the reduced-tier boundary."""

from __future__ import annotations

import copy
import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import flake_register as flake  # noqa: E402

NOW = datetime(2026, 11, 11, 18, tzinfo=UTC)
NODE = "tests/unit/test_example.py::test_example"


def evidence(job, *, days=0, **extra):
    return {"run": 123, "job": job, "at": (NOW - timedelta(days=days)).isoformat(), **extra}


def row(ident="a", *, scope="test", lane="fast", platforms=None):
    entry = {"id": ident, "scope": scope, "status": "open", "lane": lane, "platforms": platforms or ["windows"],
             "class": "race", "cause": "unestablished", "owner": "CI", "evidence": [evidence(1)]}
    if scope == "test":
        entry["test"] = NODE
    return entry


def document(*entries):
    return {"schema": flake.SCHEMA, "entries": list(entries), "census": []}


def source(path):
    return "def test_example(): pass\n" if path == "tests/unit/test_example.py" else None


def load(doc):
    return flake.load_register(yaml.safe_dump(doc), source)


def test_the_checked_in_seed_passes_validation():
    doc = flake.load_register((ROOT / flake.REGISTER).read_text(encoding="utf-8"))
    assert doc["entries"] and doc["census"]
    entries = {entry["id"]: entry for entry in doc["entries"]}
    regression = entries["windows-regression-no-response"]["evidence"]
    original = {120711840907, 120905228257, 120955536309, 123229668024, 128425197424, 128447670590,
                128603423719, 128756854110, 128816686865, 128825870593, 128839449841, 129513622219, 130116078982}
    assert original <= {row["job"] for row in regression if row.get("kind", "sighting") == "sighting"}
    diagnostic, = [row for row in regression if (row["run"], row["job"]) == (43054294887, 130639497975)]
    assert diagnostic["kind"] == "diagnostic"
    integration = entries["windows-integration-no-response"]["evidence"]
    crashed, = [row for row in integration if (row["run"], row["job"]) == (42922658468, 130216276102)]
    assert len(crashed["nodes"]) == 2


@pytest.mark.parametrize(("field", "value", "message"), [
    ("owner", "", "owner"), ("evidence", [], "evidence"),
    ("test", "tests/unit/test_example.py::test_renamed", "does not exist"),
    ("lane", "vertical", "shadow"), ("platforms", ["windows", "windows"], "distinct"),
    ("evidence", [evidence(1, kind="diagnostic")], "sighting evidence"),
])
def test_open_entries_refuse_missing_or_stale_authority(field, value, message):
    entry = row()
    assert load(document(entry))["entries"] == [entry]
    entry[field] = value
    with pytest.raises(flake.InvalidRegister, match=message):
        load(document(entry))


def test_session_entries_use_the_lane_instead_of_a_test_node():
    entry = row(scope="session", lane="regression*")
    assert load(document(entry))["entries"] == [entry]
    entry["lane"] = "*"
    with pytest.raises(flake.InvalidRegister, match="shadow"):
        load(document(entry))


@pytest.mark.parametrize("failure", ["absence", "recurrence", "clock", "renamed proof"])
def test_closing_needs_a_cause_and_a_deterministic_existing_test(failure):
    entry = {**row(), "status": "closed"}
    closure = {"pr": 101, "cause": "ordered the writes", "test": NODE, "proof": "fixed order"}
    assert load(document({**entry, "closure": closure}))
    if failure == "clock":
        entry["closure"] = {**closure, "proof": "timing"}
    elif failure == "renamed proof":
        entry["closure"] = {**closure, "test": NODE + "_renamed"}
    elif failure == "recurrence":
        entry["evidence"].append(evidence(2))
    with pytest.raises(flake.InvalidRegister, match="closure needs"):
        load(document(entry))


def test_duplicate_keys_ids_and_evidence_fail_closed():
    text = yaml.safe_dump(document(row()))
    with pytest.raises(flake.InvalidRegister, match="duplicate mapping key"):
        flake.load_register(text + f"schema: {flake.SCHEMA}\n", source)
    with pytest.raises(flake.InvalidRegister, match="duplicate entry ID"):
        load(document(row(), row()))
    with pytest.raises(flake.InvalidRegister, match="duplicate evidence"):
        load(document({**row(), "evidence": [evidence(1), evidence(1)]}))


def test_queue_orders_two_three_and_four_and_excludes_old_closed_and_diagnostic_evidence():
    entries = [row("two"), row("three"), row("four"), {**row("closed"), "status": "closed"}]
    entries[0]["evidence"] += [evidence(6, days=7), evidence(7, days=8), evidence(8, kind="diagnostic")]
    sightings = [
        (ident, evidence(job))
        for ident, job in (("two", 1), ("three", 2), ("three", 3), ("four", 2), ("four", 3), ("four", 4),
                           ("closed", 2), ("unregistered", 2))
    ]
    assert flake.queue(document(*entries), sightings, NOW) == [
        ("four", 4, True), ("three", 3, True), ("two", 2, False),
    ]


def test_records_recent_evidence_once_without_reopening_a_closed_entry():
    doc = document(row(), {**row("closed"), "status": "closed"})
    recent = [("a", evidence(2)), ("a", evidence(3, days=8)), ("a", evidence(1)), ("closed", evidence(4))]
    assert flake.record(doc, recent, NOW) == 1
    assert flake.record(doc, recent, NOW) == 0
    assert doc["entries"][0]["evidence"] == [evidence(1), evidence(2)]


def _index(rows, *, member="sightings.json"):
    data = io.BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(member, json.dumps(rows))
    return data.getvalue()


def test_index_listing_filters_by_name_and_reads_recent_rows_after_older_ones(monkeypatch):
    def artifact(ident, days, *, expired=False):
        return {"id": ident, "workflow_run": {"id": 123}, "expired": expired,
                "created_at": evidence(1, days=days)["at"], "size_in_bytes": 120}

    def pages(repo, endpoint, key):
        assert (repo, endpoint, key) == ("o/r", "actions/artifacts?per_page=100&name=flake-sighting-index", "artifacts")
        yield from [artifact(1, 8), artifact(2, 7), artifact(3, 1, expired=True)]

    def read(endpoint):
        assert endpoint == "repos/o/r/actions/artifacts/2/zip"
        return _index([{"entry": "a", "job": 2, "at": evidence(2, days=7)["at"], "observation": "one"}])

    monkeypatch.setattr(flake, "_pages", pages)
    monkeypatch.setattr(flake, "_gh_read", read)
    assert list(flake.recent_index_sightings("o/r", NOW - flake.WINDOW)) == [
        ("a", evidence(2, days=7, observation="one")),
    ]


@pytest.mark.parametrize("data", [b"bad zip", _index([], member="../sightings.json"), _index([{"entry": "a"}])])
def test_index_reader_refuses_bad_archives_and_rows(data):
    with pytest.raises(flake.InvalidRegister, match="invalid flake sighting index"):
        list(flake.index_sightings(data, 123))


def test_session_sightings_use_annotations_and_a_live_cancel_not_setup_or_a_quick_cancel():
    started = (NOW - timedelta(minutes=10)).isoformat()
    pytest_step = {"name": "Run python -m pytest", "started_at": started}
    setup = {"name": "Run ./.github/actions/setup-aew", "started_at": started}
    runs = [{"id": 123, "conclusion": "cancelled", "updated_at": (NOW - timedelta(minutes=5)).isoformat()},
            {"id": 124, "conclusion": "cancelled", "updated_at": (NOW - timedelta(seconds=5)).isoformat()},
            {"id": 125, "conclusion": "success"}]

    def job(ident, steps, *, active=False, platform="windows"):
        return {"id": ident, "name": f"regression 2/3 ({platform}-latest)", "started_at": started, "steps": steps,
                "status": "in_progress" if active else "completed", "conclusion": None if active else "cancelled"}

    def jobs(run):
        assert run["id"] != 125
        return ([job(1, [pytest_step]), job(2, []), job(3, [pytest_step], active=True), job(5, [setup]),
                 job(6, [pytest_step], platform="ubuntu")]
                if run["id"] == 123 else [job(4, [pytest_step], active=True)])

    def annotations(ident):
        assert ident in {1, 2}
        return [{"message": "The job has exceeded the maximum execution time of 34m0s"}]

    doc = document(row("session", scope="session", lane="regression"))
    got = list(flake.session_sightings(doc, runs, jobs, annotations, NOW))
    assert [(ident, item["job"]) for ident, item in got] == [("session", 1), ("session", 2), ("session", 3)]


def test_check_suites_read_job_evidence_in_batches_across_attempts(monkeypatch):
    started = (NOW - timedelta(minutes=10)).isoformat()
    runs = [
        {"id": 1, "node_id": "mixed", "conclusion": "failure"},
        {"id": 2, "node_id": "no-cancel", "conclusion": "failure"},
        {"id": 3, "node_id": "still-running", "conclusion": "cancelled", "updated_at": started},
        {"id": 4, "node_id": "prior-attempt", "conclusion": "success", "run_attempt": 2},
        {"id": 5, "node_id": "green", "conclusion": "success"},
    ]

    def conn(*nodes):
        return {"pageInfo": {"hasNextPage": False}, "nodes": list(nodes)}

    def check(job, *, active=False, setup=False):
        return {"id": f"check-{job}", "name": "regression 4/4 (windows-latest)", "databaseId": job,
                "startedAt": started,
                "status": "IN_PROGRESS" if active else "COMPLETED", "conclusion": None if active else "CANCELLED",
                "steps": conn({"name": "Set up job" if setup else "pytest --lane regression", "startedAt": started}),
                "annotations": conn({"message": "The job has exceeded the maximum execution time of 34m0s"})}

    def gh(endpoint, flag, query, *ids):
        assert endpoint == "graphql" and flag == "-f"
        if "... on CheckRun {" in query:
            assert ids == tuple(arg for job in (11, 31, 41, 42) for arg in ("-f", f"ids[]=check-{job}"))
            return {"data": {"nodes": [check(11), check(31, active=True), check(41), check(42, setup=True)]}}
        assert "checkType: ALL" in query
        assert ids == tuple(arg for run in runs[:-1] for arg in ("-f", f"ids[]={run['node_id']}"))
        suites = [(conn(check(11)), conn()), (conn(), conn()), (conn(), conn(check(31, active=True))),
                  (conn(check(41), check(42, setup=True)), conn())]
        return {"data": {"nodes": [
            {"id": run["node_id"], "checkSuite": {"cancelled": cancelled, "active": active}}
            for run, (cancelled, active) in zip(runs[:-1], suites, strict=True)
        ]}}

    def pages(_repo, endpoint, _key=None):
        if endpoint.startswith("actions/workflows/ci.yml/runs?"):
            yield from runs
        else:
            assert endpoint.startswith(("actions/artifacts?", "actions/workflows/nightly.yml/runs?"))

    monkeypatch.setattr(flake, "_gh_json", gh)
    monkeypatch.setattr(flake, "_pages", pages)
    doc = document(row("session", scope="session", lane="regression"))
    assert [(item["run"], item["job"]) for _, item in flake.github_sightings(doc, "o/r", NOW)] == [
        (1, 11), (3, 31), (4, 41),
    ]


def test_queue_keeps_the_census_and_diagnostics_out_of_eligibility():
    doc = document(row())
    doc["census"] = [{"test": NODE, "platform": "windows", "lane": "fast", "evidence": [evidence(8)]}]
    assert load(copy.deepcopy(doc))["census"] == doc["census"]
    assert flake.queue(doc, (), NOW) == [("a", 1, False)]
    doc["census"][0]["evidence"] = []
    with pytest.raises(flake.InvalidRegister, match="at least one item of evidence"):
        load(doc)
