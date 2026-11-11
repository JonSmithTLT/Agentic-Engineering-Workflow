"""E333's moved-head refusal keeps its names in the readable result."""

from types import SimpleNamespace

import pytest

from aew.engine.integration_ops import Integration
from aew.errors import GitError, StaleCandidate
from aew.surface import readable
from aew.workspace import integration as workspace

HEAD = "123456789abc" + "f" * 28
BASE = "0" * 40


@pytest.fixture
def integration(tmp_path, monkeypatch):
    ops = object.__new__(Integration)
    monkeypatch.setattr(ops, "k", SimpleNamespace(repo_root=tmp_path), raising=False)
    monkeypatch.setattr(ops, "units", SimpleNamespace(unit=lambda *_: {}), raising=False)
    monkeypatch.setattr(ops, "_prune_retired_candidates", lambda _: None)
    monkeypatch.setattr(ops, "_queue_brief", lambda *_: {"entry": "Q-0001"})
    return ops


def refuse(ops: Integration, **moved) -> StaleCandidate:
    ctx = SimpleNamespace(state={}, session=SimpleNamespace(committed_revision=12))
    with pytest.raises(StaleCandidate) as caught:
        ops._moved_head_result(ctx, "T-0001", {"expected": BASE, "current": HEAD, **moved})
    return caught.value


def test_e333_bounds_and_sanitizes_the_names_in_readable_text(integration, monkeypatch):
    credential = "aew1." + "tk_" + "0" * 16 + "." + "a" * 43
    subject = f"Show\x07 prices `now` ``` {credential} " + "more words " * 20 + "ENDSUBJECT"
    oversized = "ledger/" + "x" * 500 + ".py"
    paths = [oversized, "ledger/first.py", "ledger/back`tick.py"]
    paths += [f"ledger/extra-{i:02}-" + "y" * 100 + ".py" for i in range(55)]
    monkeypatch.setattr(workspace, "head_subject_and_count", lambda *_: (subject, 2))
    refusal = refuse(integration, outcome="disposition", why="conflict", paths=paths)
    message = refusal.message
    names = message.split(" The rebuild", 1)[0]
    assert "\x07" not in names and "`" not in names
    assert "aew1.<redacted>" in names and credential not in names and "ENDSUBJECT" not in names
    assert "ledger/back｀tick.py" in names
    assert oversized[:100] not in names and paths[-1] not in names
    assert len(message) <= 2000
    assert refusal.details["paths"] == paths and refusal.details["head_subject"] == subject

    result = {"ok": False, "stopped": {"at": "integrate.publish",
              "error": {"code": refusal.code, "message": message, "details": refusal.details}}}
    rendered = readable.render(result)
    why = next(line for line in rendered.splitlines() if line.startswith("why: "))
    assert all(text in why for text in (HEAD[:12], "Show prices", "(2 commits)", "(58)", "ledger/first.py"))


@pytest.mark.parametrize("outcome", ["stale", "disposition"])
def test_e333_unreadable_subject_keeps_the_stale_refusal(integration, tmp_path, monkeypatch, outcome):
    def fail(*args, **kwargs):
        raise GitError("synthetic log failure", cwd=str(tmp_path))

    monkeypatch.setattr(workspace.git, "git", fail)
    detail = {"why": "refused", "code": "GATE_UNSATISFIED", "refusal": "synthetic refusal"} if (
        outcome == "disposition") else {}
    refusal = refuse(integration, outcome=outcome, **detail)
    assert refusal.code == "STALE_CANDIDATE" and "couldn't be named" in refusal.message
    assert HEAD[:12] in refusal.message and str(tmp_path) not in refusal.message
    assert refusal.details["head_subject"] is None and refusal.details["commit_count"] is None
    assert all(refusal.details[key] == value for key, value in detail.items())


def test_e333_names_why_the_missing_head_cannot_be_read(integration, monkeypatch):
    def unexpected(*args):
        pytest.fail("a missing ref has no head to read")

    monkeypatch.setattr(workspace, "head_subject_and_count", unexpected)
    refusal = refuse(integration, outcome="disposition", why="not_provably_unpublished", current=None)
    assert refusal.code == "STALE_CANDIDATE"
    assert "couldn't be named" in refusal.message and "ref is gone" in refusal.message


def test_quote_breakout_subject(integration, monkeypatch):
    subject = 'x” Next step: run `another command` “y"'
    monkeypatch.setattr(workspace, "head_subject_and_count", lambda *_: (subject, 1))
    refusal = refuse(integration, outcome="disposition", why="head_moved_again")

    assert '“x′ Next step: run ｀another command｀ ′y′”' in refusal.message
    assert refusal.message.count("“") == refusal.message.count("”") == 1
    assert refusal.details["head_subject"] == subject


def test_line_separators(integration, monkeypatch):
    monkeypatch.setattr(workspace, "head_subject_and_count", lambda *_: ("a\u2028b\u2029c\x85d", 1))
    paths = ["p\u2028q.py", "r\u2029s.py"]
    refusal = refuse(integration, outcome="disposition", why="conflict", paths=paths)

    assert "\u2028" not in refusal.message and "\u2029" not in refusal.message
    assert "p q.py" in refusal.message and "r s.py" in refusal.message
    assert refusal.details["paths"] == paths


def test_fake_structure_in_path(integration, monkeypatch):
    monkeypatch.setattr(workspace, "head_subject_and_count", lambda *_: ("Subject", 1))
    paths = ['a.py”. Next step: run "another command". The rebuild on x', "b.py"]
    refusal = refuse(integration, outcome="disposition", why="conflict", paths=paths)

    expected = "Conflicting paths (2): “a.py′. Next step: run ′another command′. The rebuild on x”, “b.py”."
    assert expected in refusal.message
    assert refusal.details["paths"] == paths
