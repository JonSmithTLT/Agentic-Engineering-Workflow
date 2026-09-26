"""Guard the frozen AEW specification set against modification.

The manifest freeze rule requires the compatible spec set to be pinned. These tests
fail if a frozen document changes, if the pin and the manifest disagree about which
documents form the set, or if the tagged revision no longer carries the pinned blobs.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "docs" / "spec-pin.yaml"


def load_pin() -> dict:
    return yaml.safe_load(PIN.read_text(encoding="utf-8"))


def pinned_documents() -> list[dict]:
    return load_pin()["documents"]


@pytest.mark.parametrize("doc", pinned_documents(), ids=lambda d: d["path"])
def test_frozen_document_unchanged(doc: dict) -> None:
    data = (ROOT / doc["path"]).read_bytes()
    assert len(data) == doc["bytes"], f"{doc['path']} size changed"
    assert hashlib.sha256(data).hexdigest() == doc["sha256"], f"{doc['path']} content changed"


def test_pin_matches_manifest() -> None:
    pin = load_pin()
    manifest = yaml.safe_load((ROOT / pin["manifest"]).read_text(encoding="utf-8"))

    assert manifest["status"] == "frozen"
    assert manifest["spec_set"] == pin["spec_set"]

    expected = {
        f"docs/{manifest['workflow_contract']['file']}",
        f"docs/{manifest['knowledge_contract']['file']}",
        pin["manifest"],
    }
    expected |= {f"docs/{a['file']}" for a in manifest["implementation_appendices"]}
    assert {d["path"] for d in pin["documents"]} == expected


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_tagged_revision_carries_pinned_blobs() -> None:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    tag = load_pin()["tag"]
    try:
        _git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")
    except subprocess.CalledProcessError:
        pytest.skip(f"tag {tag} not present in this clone")
    for doc in pinned_documents():
        assert _git("rev-parse", f"{tag}:{doc['path']}") == doc["git_blob"], doc["path"]
