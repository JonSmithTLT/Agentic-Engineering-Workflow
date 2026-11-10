"""The registry uses the store's replace retry, without losing its bounded read or identity cache (E73).

Fault injection covers both the lstat and the open/read boundary, on both missing-file policies: no real replace
race or wall-clock threshold is needed. The HTTP maps suite retains its real writer/reader and file-type coverage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from sleep_patch import patch_sleep  # noqa: E402

from aew.dashboard import reader as R  # noqa: E402
from aew.engine import store as S  # noqa: E402
from aew.maps import store as MS  # noqa: E402


def registry_file(tmp_path):
    path = tmp_path / MS.REGISTRY_REL
    path.parent.mkdir(parents=True)
    data = {"schema": "aew/map-registry/v1", "epoch": "a" * 16, "map_revision": 1,
            "selection_id": "b" * 16, "selected": {}}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


@pytest.mark.parametrize("boundary", ["lstat_regular", "read_bounded"])
@pytest.mark.parametrize("error", [FileNotFoundError, PermissionError])
def test_a_transient_replace_error_retries_the_bounded_read(tmp_path, monkeypatch, boundary, error):
    _, data = registry_file(tmp_path)
    monkeypatch.setattr(S, "MISSING_MID_REPLACE", (FileNotFoundError,))  # Windows policy, on every test platform
    sleeps = patch_sleep(monkeypatch, S)
    original = getattr(MS, boundary)
    calls = []

    def colliding(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise error("synthetic replace collision")
        return original(*args, **kwargs)

    monkeypatch.setattr(MS, boundary, colliding)
    result = R.MapsReader(tmp_path).registry()
    assert result.state == R.PRESENT and result.data == data
    assert len(calls) == 2 and len(sleeps) == 1


@pytest.mark.parametrize("windows", [False, True])
def test_true_absence_uses_the_store_missing_file_policy(tmp_path, monkeypatch, windows):
    (tmp_path / MS.REGISTRY_REL).parent.mkdir(parents=True)  # maps exist, but none has been selected
    monkeypatch.setattr(S, "MISSING_MID_REPLACE", (FileNotFoundError,) if windows else ())
    sleeps = patch_sleep(monkeypatch, S)
    result = R.MapsReader(tmp_path).registry()
    assert result.state == R.NONE and result.revision == "none:0"
    assert len(sleeps) == (S.READ_RETRIES - 1 if windows else 0)
    assert not (tmp_path / MS.REGISTRY_REL).exists()


@pytest.mark.parametrize("boundary", ["lstat_regular", "read_bounded"])
def test_a_missing_file_is_not_retried_under_the_posix_policy(tmp_path, monkeypatch, boundary):
    registry_file(tmp_path)
    monkeypatch.setattr(S, "MISSING_MID_REPLACE", ())
    sleeps = patch_sleep(monkeypatch, S)
    calls = []

    def missing(*args, **kwargs):
        calls.append(args)
        raise FileNotFoundError("synthetic absence")

    monkeypatch.setattr(MS, boundary, missing)
    assert R.MapsReader(tmp_path).registry().state == R.NONE
    assert len(calls) == 1 and sleeps == []


@pytest.mark.parametrize("boundary", ["lstat_regular", "read_bounded"])
def test_exhausted_sharing_violations_raise_the_last_error(tmp_path, monkeypatch, boundary):
    registry_file(tmp_path)
    sleeps = patch_sleep(monkeypatch, S)
    errors = []

    def denied(*args, **kwargs):
        error = PermissionError(f"synthetic collision {len(errors)}")
        errors.append(error)
        raise error

    monkeypatch.setattr(MS, boundary, denied)
    with pytest.raises(PermissionError) as raised:
        R.MapsReader(tmp_path).registry()
    assert len(errors) == S.READ_RETRIES and len(sleeps) == S.READ_RETRIES - 1
    assert raised.value is errors[-1]


def test_the_registry_cache_tracks_identity_and_retries_before_reusing_it(tmp_path, monkeypatch):
    path, data = registry_file(tmp_path)
    reader = R.MapsReader(tmp_path)
    first = reader.registry()
    read = MS.read_bounded
    reads = []

    def counted(*args, **kwargs):
        reads.append(args)
        return read(*args, **kwargs)

    monkeypatch.setattr(MS, "read_bounded", counted)
    assert reader.registry() is first and reads == []
    # A real atomic replacement changes the identity and revision; the next read must not serve the old cache.
    data["map_revision"] = 2
    replacement = path.with_suffix(".tmp")
    replacement.write_text(json.dumps(data), encoding="utf-8")
    replacement.replace(path)
    monkeypatch.setattr(S, "MISSING_MID_REPLACE", (FileNotFoundError,))
    sleeps = patch_sleep(monkeypatch, S)
    lstat = MS.lstat_regular
    calls = []

    def colliding(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise FileNotFoundError("synthetic mid-replace absence")
        return lstat(*args, **kwargs)

    monkeypatch.setattr(MS, "lstat_regular", colliding)
    second = reader.registry()
    assert second.state == R.PRESENT and second.data == data and second is not first
    assert len(reads) == 1 and len(sleeps) == 1
    assert reader.registry() is second and len(reads) == 1


@pytest.mark.parametrize("kind,problem", [("directory", "not_a_file"), ("oversized", "too_large"),
                                         ("malformed", "malformed")])
def test_invalid_files_remain_invalid_without_replace_backoff(tmp_path, monkeypatch, kind, problem):
    path, _ = registry_file(tmp_path)
    if kind == "directory":
        path.unlink()
        path.mkdir()
    else:
        path.write_bytes(b"x" * (R.REGISTRY_MAX + 1) if kind == "oversized" else b"{bad json")
    sleeps = patch_sleep(monkeypatch, S)
    result = R.MapsReader(tmp_path).registry()
    assert result.state == R.INVALID and result.problem == problem
    assert sleeps == []


@pytest.mark.parametrize("windows", [False, True])
def test_an_absent_maps_directory_returns_none_without_backoff_and_is_not_cached(tmp_path, monkeypatch, windows):
    monkeypatch.setattr(S, "MISSING_MID_REPLACE", (FileNotFoundError,) if windows else ())
    sleeps = patch_sleep(monkeypatch, S)
    reader = R.MapsReader(tmp_path)
    assert reader.registry().state == R.NONE
    assert sleeps == [] and not (tmp_path / MS.REGISTRY_REL).parent.exists()
    _, data = registry_file(tmp_path)  # the first selection creates the directory; no cached absence hides it
    result = reader.registry()
    assert result.state == R.PRESENT and result.data == data and sleeps == []


@pytest.mark.parametrize("error", [FileNotFoundError, PermissionError])
def test_a_replace_during_the_identity_recheck_never_reads_invalid(tmp_path, monkeypatch, error):
    """Review M2 repro: a second replace collides with the identity-change branch's own lstat."""
    _, data = registry_file(tmp_path)
    monkeypatch.setattr(S, "MISSING_MID_REPLACE", (FileNotFoundError,))
    sleeps = patch_sleep(monkeypatch, S)
    real_lstat, real_read = MS.lstat_regular, MS.read_bounded
    lstats, reads = [], []

    def lstat(*args, **kwargs):
        lstats.append(args)
        if len(lstats) == 2:  # _regular's re-check, during the next replace
            raise error("synthetic mid-replace")
        return real_lstat(*args, **kwargs)

    def read(*args, **kwargs):
        reads.append(args)
        if len(reads) == 1:  # replaced between lstat and open: fstat sees a new identity
            raise MS.NotARegularFile("not_a_file")
        return real_read(*args, **kwargs)

    monkeypatch.setattr(MS, "lstat_regular", lstat)
    monkeypatch.setattr(MS, "read_bounded", read)
    result = R.MapsReader(tmp_path).registry()
    assert (result.state, result.problem, result.data) == (R.PRESENT, None, data)
    assert len(reads) == 2 and len(sleeps) == 1


def test_a_changed_identity_between_lstat_and_open_retries_a_regular_registry(tmp_path, monkeypatch):
    _, data = registry_file(tmp_path)
    sleeps = patch_sleep(monkeypatch, S)
    real_read = MS.read_bounded
    reads = []

    def read(*args, **kwargs):
        reads.append(args)
        if len(reads) == 1:
            raise MS.NotARegularFile("not_a_file")
        return real_read(*args, **kwargs)

    monkeypatch.setattr(MS, "read_bounded", read)
    result = R.MapsReader(tmp_path).registry()
    assert result.state == R.PRESENT and result.data == data
    assert len(reads) == 2 and sleeps == []
