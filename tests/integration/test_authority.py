"""Lead authority, credentials and operator authorization (WC §5, §6; KC §7.2; AT-4b)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pytest

from conftest import IS_WINDOWS, Project, clean_env, git, run_aew


def control_bytes(p: Project) -> bytes:
    return (p.root / ".aew/state/control.yaml").read_bytes()


def all_files_text(root: Path) -> str:
    chunks = []
    for f in root.rglob("*"):
        if f.is_file() and ".git" not in f.parts:
            chunks.append(f.read_bytes().decode("utf-8", "replace"))
    return "\n".join(chunks)


# ------------------------------------------------------------------ init & candidates


def test_init_discovers_candidates_but_confers_no_authority(repo):
    p = Project(repo)
    out = p.ok("init")
    paths = {c["path"]: c for c in out["authority_candidates"]}
    assert paths["docs/adr/"]["suggested_class"] == "decisions"
    assert paths["docs/adr/"]["confidence"] == "high"
    assert paths["README.md"]["confidence"] == "low"
    listing = p.ok("authority", "list")
    assert listing["accepted"] == []
    assert all(c["status"] == "proposed" for c in listing["candidates"])
    questions = (repo / ".aew/knowledge/OPEN-QUESTIONS.md").read_text()
    for c in out["authority_candidates"]:
        assert c["id"] in questions
    # Nothing is duplicated into .aew: candidates are references only.
    assert not (repo / ".aew/knowledge/0001-use-aew.md").exists()


def test_accept_and_reject_candidates(project):
    cands = {c["path"]: c["id"] for c in project.ok("authority", "list")["candidates"]}
    res = project.lead("authority", "accept", cands["docs/adr/"], "--class", "decisions", "--decided-by", "operator")
    decision = project.root / f".aew/decisions/{res['decision']}.md"
    assert decision.exists() and "authority_acceptance" in decision.read_text()
    project.lead("authority", "reject", cands["README.md"], "--reason", "orientation only")
    listing = project.ok("authority", "list")
    assert [a["path"] for a in listing["accepted"]] == ["docs/adr/"]
    status = {c["path"]: c["status"] for c in listing["candidates"]}
    assert status["README.md"] == "rejected"
    assert project.ok("status", "--json")["contradictions"] == []


def test_manifest_edit_outside_engine_detected_and_adopted(project):
    manifest = project.root / ".aew/project.yaml"
    manifest.write_text(manifest.read_text().replace("profile: base", "profile: python"))
    cands = project.ok("authority", "list")["candidates"]
    res = project.aew("authority", "accept", cands[0]["id"], "--class", "orientation",
                      "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.returncode == 6 and res.error["code"] == "INTEGRITY_ERROR"
    assert project.ok("status", "--json")["contradictions"]
    project.lead("manifest", "adopt", "--reason", "profile corrected by operator")
    assert project.ok("status", "--json")["contradictions"] == []


# ------------------------------------------------------------------ credentials


def test_acquire_only_when_vacant(project):
    res = project.aew("lead", "acquire", "--expect-rev", str(project.rev()))
    assert res.returncode == 4 and res.error["code"] == "PERMISSION_DENIED"


def test_token_issued_in_one_process_verified_in_another(project):
    # project.token came from a separate `aew lead acquire` process; this is another process.
    cands = project.ok("authority", "list")["candidates"]
    project.lead("authority", "reject", cands[0]["id"])


@pytest.mark.parametrize("mangle", ["tamper", "malformed", "empty-secret"])
def test_forged_credentials_rejected(project, mangle):
    token = project.token
    if mangle == "tamper":
        token = token[:-1] + ("A" if token[-1] != "A" else "B")
    elif mangle == "malformed":
        token = "lead-token-please"
    else:
        token = token.rsplit(".", 1)[0] + "."
    before = control_bytes(project)
    res = project.aew("manifest", "adopt", "--reason", "x", "--token", token, "--expect-rev", str(project.rev()))
    assert res.returncode == 4 and res.error["code"] == "PERMISSION_DENIED"
    assert control_bytes(project) == before


def test_no_raw_secret_is_ever_written(project):
    secret = project.token.rsplit(".", 1)[1]
    offer = project.lead("lead", "handoff", "offer")["offer"]
    text = all_files_text(project.root) + all_files_text(project.root.parent)
    assert secret not in text
    assert offer.rsplit(".", 1)[1] not in text
    # ...while durable verifiers exist so separate processes can verify.
    assert "verifier:" in (project.root / ".aew/state/control.yaml").read_text()


# ------------------------------------------------------------------ handoff & stale writers (AT-4b)


@pytest.mark.acceptance("AT-4b")
def test_superseded_lead_rejected_after_handoff(project):
    old = project.token
    offer = project.lead("lead", "handoff", "offer")["offer"]
    accepted = project.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(project.rev()),
                          "--session-label", "lead-b")
    new = accepted["token"]
    assert accepted["generation"] == 2

    before = control_bytes(project)
    res = project.aew("manifest", "adopt", "--reason", "x", "--token", old, "--expect-rev", str(project.rev()))
    assert res.returncode == 3 and res.error["code"] == "STALE_AUTHORITY"
    res = project.aew("manifest", "adopt", "--reason", "x", "--token", new, "--expect-rev", str(project.rev() - 1))
    assert res.returncode == 3 and res.error["code"] == "STALE_REVISION"
    assert control_bytes(project) == before

    decision = accepted["decision"]
    assert "authority_transfer" in (project.root / f".aew/decisions/{decision}.md").read_text()
    assert (project.root / ".aew/state/HANDOFF.md").exists()


def test_pending_handoff_freezes_outgoing_lead(project):
    project.lead("lead", "handoff", "offer")
    cands = project.ok("authority", "list")["candidates"]
    res = project.aew("authority", "reject", cands[0]["id"], "--token", project.token,
                      "--expect-rev", str(project.rev()))
    assert res.returncode == 4
    project.lead("lead", "handoff", "cancel")
    project.lead("authority", "reject", cands[0]["id"])


@pytest.mark.acceptance("AT-4b")
def test_takeover_cannot_be_self_authorized(project):
    rev = project.rev()
    before = control_bytes(project)
    attempts = [
        (["--reason", "lead lost"], None, None),
        (["--reason", "lead lost"], {"AEW_OPERATOR_CONFIRMED": "1", "AEW_OPERATOR": "yes"}, "yes\ny\n"),
        (["--reason", "lead lost", "--operator-confirmed"], None, None),
        (["--reason", "lead lost", "--yes"], None, "yes\n"),
    ]
    for extra, env, stdin in attempts:
        res = project.aew("lead", "takeover", "--expect-rev", str(rev), *extra, env=env, input=stdin)
        assert res.returncode != 0
        code = json.loads(res.stderr)["error"]["code"] if res.stderr.startswith("{") else "USAGE"
        assert code in {"OPERATOR_AUTHORIZATION_REQUIRED", "USAGE"}, res.stderr
    assert control_bytes(project) == before
    assert project.ok("lead", "show")["generation"] == 1


def _pty_takeover(root: Path, rev: int, label: str) -> dict:
    import pty
    import select

    argv = [sys.executable, "-m", "aew", "-C", str(root), "lead", "takeover", "--expect-rev", str(rev),
            "--reason", "Lead session lost", "--session-label", label]
    pid, fd = pty.fork()
    if pid == 0:  # child: controlling terminal is the pty slave
        os.execvpe(argv[0], argv, clean_env())
    buf = b""
    answered = False
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 1.0)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if not answered:
            match = re.search(rb"confirmation code ([0-9A-F]{6})", buf)
            if match:
                os.write(fd, match.group(1) + b"\n")  # the operator reads the screen and types
                answered = True
    _, status = os.waitpid(pid, 0)
    text = buf.decode("utf-8", "replace").replace("\r\n", "\n")
    assert os.waitstatus_to_exitcode(status) == 0, text
    return json.loads(text[text.index("{", text.index("> ")):])


@pytest.mark.acceptance("AT-4b")
@pytest.mark.serial  # a real pseudo-terminal and a forked child answering within a deadline
@pytest.mark.skipif(
    IS_WINDOWS,
    reason="POSIX pty operator path. A Windows console session would appear on the developer desktop, so on "
           "Windows the refusal path is tested here and AT-1 substitutes the terminal channel in-process",
)
def test_operator_authorized_takeover_supersedes_everyone(project):
    a_token = project.token
    offer = project.lead("lead", "handoff", "offer")["offer"]
    b_token = project.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(project.rev()))["token"]
    rev = project.rev()
    result = _pty_takeover(project.root, rev, "lead-c")
    assert result["generation"] == 3
    c_token = result["token"]
    for stale in (a_token, b_token):
        res = project.aew("manifest", "adopt", "--reason", "x", "--token", stale, "--expect-rev", str(project.rev()))
        assert res.error["code"] == "STALE_AUTHORITY"
    decision = (project.root / f".aew/decisions/{result['decision']}.md").read_text()
    assert "operator-tty" in decision and "Lead session lost" in decision
    cands = project.ok("authority", "list")["candidates"]
    project.token = c_token
    project.lead("authority", "reject", cands[0]["id"])


@pytest.mark.acceptance("AT-7")
def test_worktree_copy_of_aew_is_not_an_authority(project, tmp_path):
    git("add", "-A", ".aew", cwd=project.root)
    git("commit", "-q", "-m", "commit aew state", cwd=project.root)
    wt = tmp_path / "rogue-worktree"
    git("worktree", "add", "-q", str(wt), "HEAD", cwd=project.root)
    res = run_aew("-C", str(wt), "status", "--json")
    assert res.returncode == 6 and res.error["code"] == "WORKSPACE_NOT_AUTHORITY"
