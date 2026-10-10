"""The evaluator/arm-host split's core (register F19; F19 plan v5 S4; ADR-0018): one task released to an arm host
through a transport, never run on the evaluator; registered before its bundle leaves; every bundle verified against
its manifest under hostile receive; every step in a hash-chained release ledger; and a result finalized in
``score_run``'s shape with each fact labelled by who attests it. Synthetic cases only.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import stat
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import armhost, campaign, fixture, hidden, prereg, runner, transport  # noqa: E402
from aew_eval.armhost import Agent  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.release import GENESIS, ReleaseLedger, RunTerms, build_bundle, run_manifest, task_bytes  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402
from aew_eval.transport import (  # noqa: E402
    MANIFEST_NAME,
    Entry,
    Limits,
    LocalTransport,
    RecordingTransport,
    TransferError,
    Transport,
    check_path,
    decode_frame,
    encode_frame,
    limits_record,
    load_limits,
    manifest_of,
    pack,
    read_frame,
    receive,
)

FIX = {"write": "calc.py", "content": "def add(a, b):\n    return a + b\n"}
CHECKS = '''
import sys

def checks(tree, run):
    ran = run([sys.executable, "-c", "import calc; print(calc.add(2, 3))"])
    yield "add(2, 3) is 5", ran.stdout.strip() == "5", ran
'''
TERMS = RunTerms(seal_sha256="a" * 64, treatment_sha256="b" * 64, cap_usd=5.0, wall_s=120.0, max_publications=3,
                 envelope_duration_s=7200)
ORACLE_CANARY = "ORACLE-CANARY-7f3c1e"
OTHER_CASE_CANARY = "OTHER-CASE-CANARY-91ab2d"
PREREG_CANARY = "PREREG-CANARY-c0ffee"


def make_case(root: Path, cid: str, commitment: str | None, *, body: str = "def add(a, b):\n    return a - b\n",
              task: str | None = "Make add add.\n") -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text(body, encoding="utf-8", newline="\n")
    manifest = {"schema": "aew/eval-case/v1", "id": cid, "family": "demo", "fixture": {"base": "base"},
                "hidden_sha256": commitment, "control_of": None}
    if task is not None:
        manifest["task"] = task
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def make_oracle(hidden_root: Path, cid: str, checks: str = CHECKS) -> Path:
    oracle = hidden_root / "cases" / cid / "oracle"
    oracle.mkdir(parents=True)
    (oracle / "checks.py").write_text(checks, encoding="utf-8", newline="\n")
    return oracle


def plan_for(case_paths: list[Path], *, steps: list | None = None, held_out: tuple[str, ...] = (),
             kind: str = "scripted",
             question: str = "Does the reference fix the bug?") -> dict:
    cases = [fixture.load(p) for p in case_paths]
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "demo", "question": question,
        "arms": [{"id": "ref", "kind": kind, "description": "the reference edit",
                  "config": {"steps": [FIX] if steps is None else steps}}],
        "cases": [{"id": c.id, "family": "demo", "sha256": fixture.case_sha256(c),
                   "hidden_sha256": c.manifest["hidden_sha256"], "control_of": None} for c in cases],
        "profiles": {"roles": {"lead": "none"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "fixed", "metrics": [{"name": "fixed", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["invalid_measurement", "runner_lost"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": list(held_out),
        "scoring": {"hidden_channel": "aew_eval.hidden", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "an exposed case leaves the held-out pool", "amendment_policy": "a change is a new id",
    }
    return prereg.freeze(record, by="tester")


def cell_of(f: dict, case: str) -> str:
    return next(o["cell"] for o in f["assignment"]["order"] if o["case"] == case)


def release(f: dict, cases: dict[str, Path], tmp_path: Path, transport: Transport, *, case: str = "C1",
            name: str = "r1", **kw) -> dict:
    return campaign.run_released_cell(f, ledger_dir=tmp_path / "ledger", cell=cell_of(f, case), cases=cases,
                                      transport=transport, collect_root=tmp_path / "collected", run_name=name,
                                      terms=TERMS, **kw)


def local(tmp_path: Path, **kw) -> LocalTransport:
    return LocalTransport(tmp_path / "armhost", **kw)


def nothing_registered(tmp_path: Path) -> bool:
    return not (tmp_path / "ledger" / "attempts.jsonl").exists()


def tar_of(*members: tuple[tarfile.TarInfo, bytes | None], manifest: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
        if manifest is not None:
            raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
            info = tarfile.TarInfo(MANIFEST_NAME)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return buf.getvalue()


def member(name: str, *, data: bytes = b"", kind: bytes = tarfile.REGTYPE, target: str = "") -> tuple:
    info = tarfile.TarInfo(name)
    info.type, info.linkname = kind, target
    info.size = len(data) if kind == tarfile.REGTYPE else 0
    return info, data if kind == tarfile.REGTYPE else None


def everything_under(path: Path) -> set[str]:
    return {p.relative_to(path).as_posix() for p in path.rglob("*")}


# ---------------------------------------------------------------------------------------------- the release

def test_no_planted_oracle_or_other_case_string_crosses_the_transport(tmp_path):
    secret = tmp_path / "private"
    oracle = make_oracle(secret, "C1", CHECKS + f"\n# {ORACLE_CANARY}\n")
    c1 = make_case(tmp_path / "c1", "C1", hidden.content_sha256(oracle))
    c2 = make_case(tmp_path / "c2", "C2", None, body=f"# {OTHER_CASE_CANARY}\n", task=f"{OTHER_CASE_CANARY}\n")
    f = plan_for([c1, c2], question=f"Does it work? {PREREG_CANARY}")
    rec = RecordingTransport(local(tmp_path))
    record = release(f, {"C1": c1, "C2": c2}, tmp_path, rec, hidden_root=secret)
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("error"))
    crossed = rec.crossed()
    assert [verb for d, verb, _ in rec.frames if d == "sent"] == ["preflight", "release", "run", "collect"]
    for planted in (ORACLE_CANARY, OTHER_CASE_CANARY, PREREG_CANARY, "C2", f["canonical_sha256"],
                    hidden.content_sha256(oracle), str(secret), str(tmp_path / "ledger"), "hidden_sha256"):
        assert planted.encode("utf-8") not in crossed, planted
    assert b"Make add add." in crossed  # the released task itself does cross


def test_the_attempt_is_registered_before_the_bundle_leaves(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    seen: dict[str, Any] = {}

    def check(verb: str, message: dict) -> None:
        attempts = AttemptLedger(tmp_path / "ledger", f).attempts() if (tmp_path / "ledger").exists() else {}
        if verb == "preflight":
            seen["preflight"] = dict(attempts)
        if verb == "release":
            seen["release"] = attempts["demo/r1"].registered["release"]
            seen["sent"] = message["args"]["bundle_sha256"]

    record = release(f, {"C1": case}, tmp_path, RecordingTransport(local(tmp_path), on_call=check))
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("error"))
    assert seen["preflight"] == {}  # nothing registered while the host is preflighted
    assert seen["release"]["bundle_sha256"] == seen["sent"]  # registered, naming this bundle, before it left
    assert seen["release"]["host"] == "local" and seen["release"]["snapshot_uuid"] is None
    events = [ln["event"] for ln in ReleaseLedger(tmp_path / "ledger", "demo").lines()]
    assert events == ["preflight", "registered", "released", "ran", "collected", "finalized"]
    with pytest.raises(Invalid, match="release"):  # the attempt schema checks the block
        validate("aew/eval-attempt/v1", {**AttemptLedger(tmp_path / "ledger", f).lines()[0],
                                          "release": {"host": "local"}})


def test_the_campaign_path_never_runs_an_arm_on_the_evaluator(tmp_path):
    source = (ROOT / "eval" / "aew_eval" / "campaign.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {f"{n.module}.{a.name}" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                 for a in n.names}
    assert not {m for m in imported if m.split(".")[-1] in ("runner", "raw", "subprocess", "run_cell", "arm_for",
                                                               "RawArm", "ARMS")}, imported
    called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not called & {"run", "build", "build_files", "run_cell", "arm_for", "Popen"}, called
    # And at run time: the arm ran in the arm host's process and directory; the evaluator only received its tree.
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    record = release(f, {"C1": case}, tmp_path, local(tmp_path))
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("error"))
    assert record["environment"]["pid"] != os.getpid()
    assert (tmp_path / "armhost" / "runs" / "demo" / "r1" / "repo" / ".git").is_dir()
    assert not any(p.name == ".git" for p in (tmp_path / "collected").rglob("*"))
    assert (tmp_path / "collected" / "r1" / "tree" / "calc.py").read_text(encoding="utf-8") == FIX["content"]
    assert record["outcome"]["changed_paths"] == ["calc.py"]


@pytest.mark.parametrize("kind", ["raw", "aew"])
def test_a_model_arm_is_refused_before_anything_is_registered_or_released(tmp_path, kind):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case], kind=kind)
    rec = RecordingTransport(local(tmp_path))
    with pytest.raises(campaign.Refused, match="scripted arm only"):
        release(f, {"C1": case}, tmp_path, rec)
    assert nothing_registered(tmp_path) and rec.frames == []


def test_a_held_out_case_is_never_released_on_a_preflight_that_establishes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(hidden, "scoring_contained", lambda: True)  # the evaluator's side is not what is tested
    secret = tmp_path / "private"
    oracle = make_oracle(secret, "C1")
    case = make_case(tmp_path / "c", "C1", hidden.content_sha256(oracle))
    f = plan_for([case], held_out=("C1",))
    rec = RecordingTransport(local(tmp_path))
    with pytest.raises(campaign.Refused, match="did not establish corpus isolation"):
        release(f, {"C1": case}, tmp_path, rec, hidden_root=secret)
    assert nothing_registered(tmp_path)
    assert [verb for d, verb, _ in rec.frames if d == "sent"] == ["preflight"]  # nothing released
    events = ReleaseLedger(tmp_path / "ledger", "demo").lines()
    assert [(e["event"], e["data"]["reason"]) for e in events] == [("preflight_refused", "PREFLIGHT_REFUSED")]


# ---------------------------------------------------------------------------------------------- hostile receive

@pytest.mark.parametrize("members", [
    [member("../escape", data=b"x")],
    [member("/abs-escape", data=b"x")],
    [member("tree/../../escape", data=b"x")],
    [member("C:/escape", data=b"x")],
    [member("tree\\..\\..\\escape", data=b"x")],
    [member("tree/.git/hooks/post-checkout", data=b"x")],
    [member("tree/lnk", kind=tarfile.SYMTYPE, target=".."), member("tree/lnk/escape", data=b"x")],
    [member("tree/a", data=b"x"), member("tree/hard", kind=tarfile.LNKTYPE, target="tree/a")],
    [member("tree/dev", kind=tarfile.CHRTYPE)],
    [member("tree/blk", kind=tarfile.BLKTYPE)],
    [member("tree/fifo", kind=tarfile.FIFOTYPE)],
    [member("tree/Dir/x", data=b"x"), member("tree/dir/y", data=b"y")],
    [member("tree/a", data=b"x"), member("tree/a", data=b"y")],
], ids=["dotdot", "absolute", "inner-dotdot", "drive", "backslash", "dot-git", "through-a-link", "hard-link",
        "char-device", "block-device", "fifo", "case-twin", "duplicate"])
def test_a_result_tar_with_traversal_or_devices_writes_nothing_outside_its_directory(tmp_path, members):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("unchanged", encoding="utf-8")
    before = everything_under(tmp_path)
    dest = tmp_path / "in" / "recv"
    dest.parent.mkdir()
    with pytest.raises(TransferError) as refused:
        receive(tar_of(*members, manifest=manifest_of([])), dest)
    assert refused.value.code in ("UNSAFE_PATH", "PATH_CONFLICT", "ENTRY_TYPE_REFUSED"), refused.value
    assert not dest.exists()  # what it wrote is removed with it
    assert everything_under(tmp_path) == before | {"in"}
    assert (outside / "keep").read_text(encoding="utf-8") == "unchanged"


def test_a_link_arrives_only_as_a_data_entry(tmp_path):
    data, digest = pack([Entry("tree/ok.txt", "file", data=b"ok\n"), Entry("tree/lnk", "link", target="/etc/passwd"),
                         Entry("tree/up", "link", target="../../outside")])
    got = receive(data, tmp_path / "recv", expected_sha256=digest)
    assert got.links == {"tree/lnk": "/etc/passwd", "tree/up": "../../outside"}
    assert set(got.files) == {"tree/ok.txt"}
    assert everything_under(tmp_path / "recv") == {"tree", "tree/ok.txt"}  # no link was created
    # A link in an arm's work tree comes back the same way, recorded as changed, never exported.
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    class Linking(LocalTransport):
        def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
            message, _ = decode_frame(request, what="request", limits=self.limits, max_payload=self.limits.tar_bytes())
            if message["verb"] == "collect":
                link = self.root / "runs" / "demo" / "r1" / "repo" / "pw"
                if sys.platform == "win32":  # a junction needs no privilege
                    import _winapi

                    _winapi.CreateJunction(str(elsewhere), str(link))
                else:
                    os.symlink("/etc/passwd", link)
            return super().exchange(request, timeout_s=timeout_s, max_reply=max_reply)

    record = release(f, {"C1": case}, tmp_path, Linking(tmp_path / "armhost"))
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("error"))
    assert "pw" in record["outcome"]["changed_paths"]
    assert not os.path.lexists(tmp_path / "collected" / "r1" / "tree" / "pw")


def test_an_oversized_reply_is_refused_with_its_reason(tmp_path):
    limits = Limits(json_bytes=1024)

    class Huge(Transport):
        host, limits = None, Limits(json_bytes=1024)

        def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
            return b'{"schema":"aew/m4h-armhost/v1","pad":"' + b"x" * 4096 + b'"}\n'

    with pytest.raises(TransferError) as refused:
        Huge().call("hello", run_id=None)
    assert refused.value.code == "REPLY_TOO_LARGE" and "1024 bytes" in str(refused.value)
    # The local transport stops reading at its bound, and says so.
    with pytest.raises(TransferError) as refused:
        local(tmp_path).exchange(encode_frame({"kind": "request", "verb": "hello", "run_id": None, "args": {}}),
                                 timeout_s=60, max_reply=8)
    assert refused.value.code == "REPLY_TOO_LARGE"
    # A payload larger than declared, or than the bound, is refused before it is read.
    frame = encode_frame({"kind": "reply", "verb": "hello", "ok": True, "error": None, "result": {}}, b"z" * 64)
    with pytest.raises(TransferError) as refused:
        decode_frame(frame, what="reply", limits=limits, max_payload=16)
    assert refused.value.code == "PAYLOAD_TOO_LARGE"
    # Bundle bounds: per file, in total, in entries.
    for small, entries, code in ((Limits(file_bytes=4), [Entry("tree/a", "file", data=b"12345")], "FILE_TOO_LARGE"),
                                 (Limits(total_bytes=6), [Entry("tree/a", "file", data=b"1234"),
                                                          Entry("tree/b", "file", data=b"1234")], "TOTAL_TOO_LARGE"),
                                 (Limits(entries=1), [Entry("tree/a", "file", data=b"1"),
                                                      Entry("tree/b", "file", data=b"2")], "TOO_MANY_ENTRIES")):
        data, _ = pack(entries)
        dest = tmp_path / f"recv-{code}"
        with pytest.raises(TransferError) as refused:
            receive(data, dest, limits=small)
        assert refused.value.code == code and not dest.exists()
        with pytest.raises(TransferError, match="OVER_BOUNDS"):
            pack(entries, limits=small)  # a sound packer never sends what the receiver refuses


def test_a_bundle_not_matching_its_manifest_is_refused(tmp_path):
    data, digest = pack([Entry("tree/calc.py", "file", data=b"def add(a, b):\n    return a + b\n")])
    tampered = data.replace(b"a + b", b"a * b")
    with pytest.raises(TransferError) as refused:
        receive(tampered, tmp_path / "r1")
    assert refused.value.code == "TRANSFER_CORRUPT"
    with pytest.raises(TransferError, match="TRANSFER_CORRUPT"):
        receive(data, tmp_path / "r2", expected_sha256="0" * 64)  # not the bundle its sender recorded
    with pytest.raises(TransferError, match="no MANIFEST.json"):
        receive(tar_of(member("tree/a", data=b"x")), tmp_path / "r3")
    for garbage in (b"not a tar at all" * 64, data[:700]):  # noise, and a tar cut short
        with pytest.raises(TransferError, match="TRANSFER_CORRUPT"):
            receive(garbage, tmp_path / "r4")
        assert not (tmp_path / "r4").exists()
    # The arm host refuses a release bundle that is not the one the evaluator registered.
    case = make_case(tmp_path / "c", "C1", None)
    snap = fixture.snapshot(fixture.load(case))
    task = task_bytes("Make add add.\n")
    manifest = run_manifest(TERMS, run_id="demo/r9", cell="C1/ref/1", task=task)
    bundle = build_bundle(snap, run_id="demo/r9", arm={"id": "ref", "kind": "scripted", "config": {}}, seeded=False,
                          task=task, manifest=manifest)
    reply = local(tmp_path).call("release", run_id="demo/r9", args={"bundle_sha256": "1" * 64}, payload=bundle.tar)
    assert not reply.ok and reply.error["code"] == "TRANSFER_CORRUPT"
    # And the evaluator refuses a collected bundle that does not match the manifest the arm host wrote.
    f = plan_for([case])

    class Tampering(LocalTransport):
        def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
            raw = super().exchange(request, timeout_s=timeout_s, max_reply=max_reply)
            return raw.replace(b"a + b", b"a * b") if b'"verb":"collect"' in raw[:raw.index(b"\n")] else raw

    record = release(f, {"C1": case}, tmp_path, Tampering(tmp_path / "armhost2"))
    # collect-side: never a bare TRANSFER_CORRUPT, which plan §2.5 treats as retryable (PR #189 review, F3)
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "RESULT_REFUSED:TRANSFER_CORRUPT"}
    assert "scoring" not in record["outcome"]


def test_a_failure_after_registration_is_counted_with_its_reason(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])

    class Dropping(LocalTransport):
        def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
            if b'"verb":"run"' in request[:request.index(b"\n")]:
                raise TransferError("TIMEOUT", "the arm host did not answer")
            return super().exchange(request, timeout_s=timeout_s, max_reply=max_reply)

    record = release(f, {"C1": case}, tmp_path, Dropping(tmp_path / "armhost"))
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "TRANSPORT_ERROR:TIMEOUT"}
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"demo/r1": "invalid_measurement"}
    assert [e["event"] for e in ReleaseLedger(tmp_path / "ledger", "demo").lines()][-2:] == ["failed", "finalized"]


# ---------------------------------------------------------------------------------------------- the record

def test_a_finalized_record_is_scoreable_by_score_run(tmp_path):
    secret = tmp_path / "private"
    oracle = make_oracle(secret, "C1")
    case = make_case(tmp_path / "c", "C1", hidden.content_sha256(oracle))
    f = plan_for([case])
    record = release(f, {"C1": case}, tmp_path, local(tmp_path), hidden_root=secret)
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("error"))
    scoring = record["outcome"]["scoring"]
    assert scoring["deferred"] is True and scoring["oracle_commitment"] == hidden.content_sha256(oracle)
    entry = runner.score_run(f, ledger_dir=tmp_path / "ledger", run_id="demo/r1", hidden_root=secret)
    assert entry["score"]["passed"] is True, entry
    assert entry["export_sha256"] == scoring["export_sha256"]


def test_the_run_record_labels_who_attests_each_fact(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    record = release(f, {"C1": case}, tmp_path, local(tmp_path))
    labels = record["outcome"]["attested_by"]
    assert set(labels.values()) <= set(campaign.ATTESTERS)
    for fact in ("environment", "harness", "wall_s", "outcome.base_commit"):  # observed on the arm host
        assert labels[fact] == campaign.GUEST, fact
    for fact in ("outcome.release", "outcome.changed_paths", "outcome.scoring", "case", "arm", "validity"):
        assert labels[fact] == campaign.EVALUATOR, fact
    # the snapshot is the evaluator's own host record until S6 checks it against the hypervisor (review F13)
    assert campaign.attester("outcome.release.snapshot_uuid") == campaign.EVALUATOR
    assert labels["outcome.scoring.export"] == campaign.MODEL  # the delivered tree is the model's work
    # The record describes the arm host, not the evaluator, and names its release and the release chain.
    assert record["environment"]["host"] == "local" and record["outcome"]["safety"]["checkout_untouched"] is None
    rel = record["outcome"]["release"]
    assert rel["chain_sha256"] in {hashlib.sha256(json.dumps(ln, sort_keys=True, separators=(",", ":"),
                                                             ensure_ascii=False).encode("utf-8")).hexdigest()
                                   for ln in ReleaseLedger(tmp_path / "ledger", "demo").lines()}
    assert ReleaseLedger(tmp_path / "ledger", "demo").verify([rel["chain_sha256"]]) == []
    manifest = json.loads((tmp_path / "armhost.state" / "runs" / "demo" / "r1" / "bundle" / "run-manifest.json")
                          .read_text(encoding="utf-8"))
    assert hashlib.sha256((tmp_path / "armhost.state" / "runs" / "demo" / "r1" / "bundle" / "run-manifest.json")
                          .read_bytes()).hexdigest() == rel["run_manifest_sha256"]
    assert manifest["task_input_sha256"] == rel["task_input_sha256"] == hashlib.sha256(b"Make add add.\n").hexdigest()


def test_nothing_the_arm_host_reports_stands_in_for_an_evaluator_fact(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])

    class Forging(LocalTransport):
        def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
            raw = super().exchange(request, timeout_s=timeout_s, max_reply=max_reply)
            message, body = decode_frame(raw, what="reply", limits=self.limits, max_payload=self.limits.tar_bytes())
            if message["verb"] == "run":
                message["result"]["outcome"]["scoring"] = {"deferred": True, "export": "/elsewhere",
                                                           "export_sha256": "0" * 64, "oracle_commitment": None}
                message["result"]["environment"]["host"] = "forged"
            return encode_frame({k: v for k, v in message.items() if k not in ("schema", "payload_bytes")}, body)

    record = release(f, {"C1": case}, tmp_path, Forging(tmp_path / "armhost"))
    assert record["validity"]["status"] == "valid", record["validity"]
    assert record["environment"]["host"] == "local"
    assert record["outcome"]["scoring"]["export"] == str((tmp_path / "collected" / "r1" / "tree").resolve())
    assert record["outcome"]["arm_outcome"]["scoring"]["export"] == "/elsewhere"  # kept, as the guest's claim


def test_the_run_manifest_carries_the_runs_terms_and_nothing_else(tmp_path):
    m = run_manifest(TERMS, run_id="demo/r1", cell="C1/ref/1", task=b"Make add add.\n")
    assert m == {"schema": "aew/m4h-run-manifest/v1", "seal_sha256": "a" * 64, "run_id": "demo/r1",
                 "cell": "C1/ref/1", "task_input_sha256": hashlib.sha256(b"Make add add.\n").hexdigest(),
                 "caps": {"usd": 5.0, "wall_s": 120.0}, "treatment_sha256": "b" * 64, "max_publications": 3,
                 "envelope_duration_s": 7200}
    with pytest.raises(Invalid, match="aew/m4h-run-manifest/v1"):
        validate("aew/m4h-run-manifest/v1", {**m, "oracle": "x"})
    with pytest.raises(Invalid, match="max_publications"):
        run_manifest(RunTerms(**{**TERMS.__dict__, "max_publications": 0}), run_id="demo/r1", cell="c", task=b"")


def test_the_armhost_imports_nothing_that_reads_the_corpus_or_the_ledgers():
    import subprocess

    probe = ("import sys; sys.path.insert(0, sys.argv[1]); import aew_eval.armhost; "
             "print(' '.join(sorted(m for m in sys.modules if m.startswith('aew'))))")
    out = subprocess.run([sys.executable, "-I", "-c", probe, str(ROOT / "eval")], capture_output=True, text=True,
                         check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.split()
    assert not {"aew_eval.hidden", "aew_eval.ledger", "aew_eval.prereg", "aew_eval.release", "aew_eval.campaign",
                "aew_eval.runner", "aew_eval.raw", "aew_eval.score_child"} & set(out), out
    assert not [m for m in out if m == "aew" or m.startswith("aew.")], out


# ---------------------------------------------------------------------------------------------- the release ledger

def test_the_release_ledger_is_append_only_and_verifies(tmp_path):
    ledger = ReleaseLedger(tmp_path, "demo")
    assert ledger.head() == GENESIS and ledger.verify() == []
    heads = [ledger.append("demo/r1", event, {"n": n}) for n, event in
             enumerate(["preflight", "registered", "released", "ran", "collected", "finalized"])]
    assert ledger.head() == heads[-1] and ledger.verify(heads) == []
    lines = ledger.path.read_bytes().split(b"\n")
    # A torn tail (an append that never returned) is ignored, then cut by the next append.
    with ledger.path.open("ab") as fh:
        fh.write(b'{"schema":"aew/m4h-rel')
    assert ledger.verify(heads) == [] and len(ledger.lines()) == 6
    heads.append(ledger.append("demo/r2", "preflight"))
    assert ledger.verify(heads) == [] and len(ledger.lines()) == 7
    good = ledger.path.read_bytes()
    # An edited line breaks the chain at the next one.
    edited = lines[2].replace(b'"n":2', b'"n":9')
    ledger.path.write_bytes(good.replace(lines[2], edited))
    assert any("line 4 does not follow" in p for p in ledger.verify(heads))
    # A removed line breaks the sequence and the chain; a removed last line drops a head a record names.
    ledger.path.write_bytes(good.replace(lines[1] + b"\n", b""))
    assert any("sequence" in p for p in ledger.verify(heads))
    ledger.path.write_bytes(good[:good.rstrip(b"\n").rfind(b"\n") + 1])
    problems = ledger.verify(heads)
    assert f"the chain no longer holds {heads[-1]}, which a run record names" in problems
    assert any("its anchor names" in p for p in problems)


def test_the_attempt_ledger_and_the_runner_are_unchanged_without_a_release(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    record = runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=cell_of(f, "C1"), cases={"C1": case},
                             work=tmp_path / "work", run_name="r1")
    assert record["validity"]["status"] == "valid"
    assert "release" not in AttemptLedger(tmp_path / "ledger", f).lines()[0]
    assert not (tmp_path / "ledger" / "releases.jsonl").exists()


def test_the_agent_runs_each_verb_once_and_in_order(tmp_path):
    agent = Agent(tmp_path / "root", state_root=tmp_path / "state")
    with pytest.raises(Exception, match="never released"):
        agent.handle("run", "demo/r1", {}, b"")
    case = make_case(tmp_path / "c", "C1", None)
    snap = fixture.snapshot(fixture.load(case))
    manifest = run_manifest(TERMS, run_id="demo/r1", cell="C1/ref/1", task=b"")
    bundle = build_bundle(snap, run_id="demo/r1", arm={"id": "ref", "kind": "scripted", "config": {"steps": [FIX]}},
                          seeded=False, task=b"", manifest=manifest)
    assert agent.handle("release", "demo/r1", {"bundle_sha256": bundle.sha256}, bundle.tar)[0] == {
        "bundle_sha256": bundle.sha256}
    with pytest.raises(Exception, match="already released"):
        agent.handle("release", "demo/r1", {"bundle_sha256": bundle.sha256}, bundle.tar)
    with pytest.raises(Exception, match="needs it ran"):
        agent.handle("collect", "demo/r1", {}, b"")
    ran, _ = agent.handle("run", "demo/r1", {"deadline_s": 60}, b"")
    assert ran["error"] is None and ran["outcome"] == {"steps": 1}
    with pytest.raises(Exception, match="needs it released"):
        agent.handle("run", "demo/r1", {}, b"")
    result, data = agent.handle("collect", "demo/r1", {}, b"")
    got = receive(data, tmp_path / "recv", expected_sha256=result["manifest_sha256"])
    assert set(got.files) == {"tree/calc.py"}


# ---------------------------------------------------------------------------------------------- PR #189 review fixes

def rewrite(raw: bytes, change) -> bytes:
    """A reply frame with its message (and payload) changed by ``change(message, body) -> body``."""
    message, body = decode_frame(raw, what="reply", limits=Limits(), max_payload=Limits().tar_bytes())
    body = change(message, body)
    return encode_frame({k: v for k, v in message.items() if k not in ("schema", "payload_bytes")}, body)


class Hooked(LocalTransport):
    """A local transport with a hook before each call (``before(verb, run_dir)``) and a rewrite of each reply
    (``after(verb, raw) -> raw``)."""

    def __init__(self, root: Path, *, before=None, after=None, **kw) -> None:
        super().__init__(root, **kw)
        self.before, self.after = before, after

    def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
        message, _ = decode_frame(request, what="request", limits=self.limits, max_payload=self.limits.tar_bytes())
        if self.before is not None:
            self.before(message["verb"], self.root / "runs" / "demo" / "r1")
        raw = super().exchange(request, timeout_s=timeout_s, max_reply=max_reply)
        return self.after(message["verb"], raw) if self.after is not None else raw


def test_a_name_that_is_not_utf8_is_listed_and_the_rest_of_the_tree_is_still_collected(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])

    def plant(verb: str, run: Path) -> None:
        if verb != "collect":
            return
        repo = run / "repo"
        if sys.platform == "win32":
            (repo / "odd\ud800.txt").write_bytes(b"x")  # a lone surrogate: NTFS holds it, UTF-8 cannot
        else:
            fd = os.open(os.fsencode(repo) + b"/odd\xff.txt", os.O_WRONLY | os.O_CREAT, 0o644)
            os.close(fd)

    record = release(f, {"C1": case}, tmp_path, Hooked(tmp_path / "armhost", before=plant))
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("arm_error"))
    assert record["outcome"]["changed_paths"] == ["calc.py"] and "scoring" in record["outcome"]
    unread = record["outcome"]["unread_paths"]
    assert len(unread) == 1 and next(iter(unread)).startswith("odd\\") and set(unread.values()) == {"unsafe-name"}
    with pytest.raises(TransferError, match="UNSAFE_PATH"):
        check_path("tree/odd\udcff.txt", "a path")


def test_the_unread_list_is_bounded_by_its_serialized_size_not_its_count():
    worst = {("aux." + "0" * 1000 + f"{n:06d}"): "unsafe-name" for n in range(5000)}
    worst |= {f"ctl{n:05d}" + "\x01" * 150: "special" for n in range(5000)}  # each control byte is six in JSON
    listed, omitted = armhost.bound_other(worst)
    assert len(json.dumps(listed)) <= armhost.OTHER_BYTES + 2
    assert omitted == len(worst) - len(listed) and omitted > 0
    frame = encode_frame({"kind": "reply", "verb": "collect", "ok": True, "error": None,
                          "result": {"manifest_sha256": "0" * 64, "other": listed, "other_omitted": omitted}})
    assert frame.index(b"\n") < Limits().json_bytes  # the reply stays under its JSON bound at its worst case


def test_a_packer_never_sends_a_bundle_the_receiver_refuses_for_its_manifest_or_wire_size(tmp_path):
    many = [Entry(f"tree/{'d' * 200}/{n:05d}", "file", data=b"") for n in range(40)]
    with pytest.raises(TransferError, match="OVER_BOUNDS.*manifest"):
        pack(many, limits=Limits(file_bytes=4096))
    deep = "/".join(["p" * 250] * 15)  # about 3,800 characters: several KiB of PAX header per entry
    long_paths = [Entry(f"tree/{deep}/{n:05d}", "file", data=b"") for n in range(40)]
    with pytest.raises(TransferError, match="OVER_BOUNDS.*on the wire"):
        pack(long_paths, limits=Limits(file_bytes=16 * 1024, total_bytes=0, entries=40))
    data, _ = pack(many)
    with pytest.raises(TransferError) as refused:  # the receiver names an oversized manifest, never TRANSFER_CORRUPT
        receive(data, tmp_path / "r", limits=Limits(file_bytes=4096))
    assert refused.value.code == "MANIFEST_TOO_LARGE"


def test_the_agents_bounds_come_from_its_host_record_and_bound_what_it_reads(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    small = Limits(file_bytes=4096)  # the release bundle fits; the file planted below does not

    def plant(verb: str, run: Path) -> None:
        if verb == "collect":
            (run / "repo" / "big.bin").write_bytes(b"x" * 10_000)

    record = release(f, {"C1": case}, tmp_path, Hooked(tmp_path / "armhost", before=plant, agent_limits=small))
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "RESULT_REFUSED:OVER_BOUNDS"}
    assert json.loads((tmp_path / "armhost.limits.json").read_text(encoding="utf-8"))["file_bytes"] == 4096
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**limits_record(Limits()), "file_bytes": 0}), encoding="utf-8")
    with pytest.raises(ValueError, match="positive"):
        load_limits(bad)
    big = tmp_path / "repo"
    big.mkdir()
    (big / "big.bin").write_bytes(b"x" * 64)
    with pytest.raises(TransferError, match="OVER_BOUNDS"):  # sized before it is read
        armhost._walk(big, Limits(file_bytes=16))


def test_a_collect_root_reached_through_a_link_still_finalizes_valid_and_scoreable(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    real = tmp_path / "real-root"
    real.mkdir()
    linked = tmp_path / "linked-root"
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(real), str(linked))
    else:
        os.symlink(real, linked, target_is_directory=True)
    record = campaign.run_released_cell(f, ledger_dir=tmp_path / "ledger", cell=cell_of(f, "C1"),
                                        cases={"C1": case}, transport=local(tmp_path), collect_root=linked,
                                        run_name="r1", terms=TERMS)
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("error"))
    assert record["outcome"]["scoring"]["export"] == str((real / "r1" / "tree").resolve())


def test_removing_the_release_ledgers_last_lines_is_detected(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    release(f, {"C1": case}, tmp_path, local(tmp_path))
    ledger = ReleaseLedger(tmp_path / "ledger", "demo")
    attempts = AttemptLedger(tmp_path / "ledger", f).attempts()
    assert ledger.verify(attempts=attempts) == []
    good = ledger.path.read_bytes()
    ledger.path.write_bytes(good[:good.rstrip(b"\n").rfind(b"\n") + 1])  # the run's finalized event
    assert any("its anchor names" in p for p in ledger.verify(attempts=attempts))
    ledger.anchor.write_text(ledger.head() + "\n", encoding="ascii")  # and the anchor rewritten to match
    assert ledger.verify(attempts=attempts) == [
        "demo/r1 is finalized, and its finalized event is missing or names another result"]
    # A trailing refusal, which no run record names, is anchored too.
    ledger.path.write_bytes(good)
    ledger.anchor.write_text(hashlib.sha256(good.rstrip(b"\n").rsplit(b"\n", 1)[-1]).hexdigest() + "\n",
                             encoding="ascii")
    assert ledger.verify(attempts=attempts) == []
    ledger.append("demo/r2", "preflight_refused", {"reason": "PREFLIGHT_REFUSED"})
    ledger.path.write_bytes(good)
    assert any("its anchor names" in p for p in ledger.verify(attempts=attempts))


def test_a_collect_entry_outside_the_tree_or_a_clashing_unread_path_is_refused(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    data, digest = pack([Entry("tree/calc.py", "file", data=FIX["content"].encode()),
                         Entry("planted", "file", data=b"x"), Entry("XXXXXunchanged.py", "link", target="x")])

    def outside(verb: str, raw: bytes) -> bytes:
        if verb != "collect":
            return raw

        def change(message, body):
            message["result"]["manifest_sha256"] = digest
            return data
        return rewrite(raw, change)

    record = release(f, {"C1": case}, tmp_path, Hooked(tmp_path / "armhost", after=outside))
    assert record["validity"]["reason_code"] == "RESULT_REFUSED:UNEXPECTED_ENTRY"
    assert "outside tree/" in record["outcome"]["arm_error"] and "error" not in record["outcome"]  # it quotes the guest

    def clash(verb: str, raw: bytes) -> bytes:
        if verb != "collect":
            return raw

        def change(message, body):
            message["result"]["other"] = {"calc.py": "special"}
            return body
        return rewrite(raw, change)

    record = release(f, {"C1": case}, tmp_path / "second", Hooked(tmp_path / "armhost2", after=clash))
    assert record["validity"]["reason_code"] == "RESULT_REFUSED:OTHER_CONFLICT"


def test_an_over_long_component_or_an_unwritable_path_is_refused_with_a_stable_code(tmp_path, monkeypatch):
    with pytest.raises(TransferError, match="UNSAFE_PATH"):
        check_path("tree/" + "n" * 256, "a path")
    with pytest.raises(TransferError) as refused:
        receive(tar_of(member("tree/" + "é" * 128, data=b"x"), manifest=manifest_of([])), tmp_path / "r1")
    assert refused.value.code == "UNSAFE_PATH"  # 256 bytes as UTF-8, though 128 characters

    real_open = os.open

    def failing_open(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:  # only the received file's creation: the clean-up's own opens still work
            raise OSError(36, "File name too long")
        return real_open(path, flags, *args, **kwargs)

    data, digest = pack([Entry("tree/a", "file", data=b"x")])
    monkeypatch.setattr(transport.os, "open", failing_open)
    with pytest.raises(TransferError) as refused:
        receive(data, tmp_path / "r2", expected_sha256=digest)
    monkeypatch.undo()
    assert refused.value.code == "WRITE_REFUSED" and not (tmp_path / "r2").exists()


def test_an_unreadable_directory_is_listed_never_silently_dropped(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "kept").mkdir(parents=True)
    (repo / "kept" / "work.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "calc.py").write_text("y = 2\n", encoding="utf-8")
    real = os.scandir

    def scandir(path):
        if Path(path).name == "kept":
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", scandir)
    entries, other = armhost._walk(repo)
    monkeypatch.undo()
    assert [e.path for e in entries] == ["calc.py"]
    assert other == {"kept": "unreadable"}


def test_a_frame_with_nan_or_bytes_after_its_payload_is_refused():
    raw = (b'{"error":null,"kind":"reply","ok":true,"payload_bytes":0,"result":{"wall_s":NaN},'
           b'"schema":"aew/m4h-armhost/v1","verb":"hello"}\n')
    with pytest.raises(TransferError, match="REPLY_MALFORMED"):
        decode_frame(raw, what="reply", limits=Limits(), max_payload=0)
    request = encode_frame({"kind": "request", "verb": "hello", "run_id": None, "args": {}}, b"ab")
    assert read_frame(io.BytesIO(request), what="request", limits=Limits(), max_payload=16)[1] == b"ab"
    with pytest.raises(TransferError, match="REQUEST_MALFORMED.*after its payload"):
        read_frame(io.BytesIO(request + b"!"), what="request", limits=Limits(), max_payload=16)


def test_a_sparse_member_is_refused(tmp_path):
    mapdata = b"1\n0\n0\n" + b"\0" * 506
    info = tarfile.TarInfo("tree/sparse")
    info.size = len(mapdata)
    info.pax_headers = {"GNU.sparse.major": "1", "GNU.sparse.minor": "0", "GNU.sparse.name": "tree/sparse",
                        "GNU.sparse.realsize": str(1 << 20)}
    with pytest.raises(TransferError) as refused:
        receive(tar_of((info, mapdata), manifest=manifest_of([])), tmp_path / "r")
    assert refused.value.code == "ENTRY_TYPE_REFUSED" and not (tmp_path / "r").exists()


def test_a_lost_collect_reply_can_be_collected_again_with_the_same_bytes(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    lost: list[bytes] = []

    def drop_first(verb: str, raw: bytes) -> bytes:
        if verb == "collect" and not lost:
            lost.append(raw)
            raise TransferError("TIMEOUT", "the reply was lost in transit")
        return raw

    hooked = Hooked(tmp_path / "armhost", after=drop_first)
    record = release(f, {"C1": case}, tmp_path, hooked)
    assert record["validity"]["reason_code"] == "TRANSPORT_ERROR:TIMEOUT"  # a lost channel, not a refused result
    again = hooked.call("collect", run_id="demo/r1")
    first = decode_frame(lost[0], what="reply", limits=Limits(), max_payload=Limits().tar_bytes())
    assert again.ok and again.payload == first[1] and again.result == first[0]["result"]
    with pytest.raises(Exception, match="already released"):  # release and run stay once-only
        Agent(tmp_path / "armhost", state_root=tmp_path / "armhost.state").handle(
            "release", "demo/r1", {"bundle_sha256": "0" * 64}, b"")


def test_every_fact_of_the_record_has_an_attester(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    record = release(f, {"C1": case}, tmp_path, local(tmp_path))

    def leaves(value, path=""):
        if isinstance(value, dict) and value and path != "outcome.attested_by":
            for k, v in value.items():
                yield from leaves(v, f"{path}.{k}" if path else k)
        else:
            yield path

    assert [p for p in leaves(record) if campaign.attester(p) is None] == []
    assert campaign.attester("outcome.unread_paths") == campaign.GUEST
    assert campaign.attester("outcome.arm_error") == campaign.GUEST
    assert campaign.attester("outcome.error") == campaign.EVALUATOR


def test_a_chatty_agent_never_blocks_the_transport(tmp_path):
    chatty = LocalTransport(tmp_path / "armhost")
    chatty.boot = "import sys; sys.stderr.write('w' * (4 << 20)); sys.stderr.flush(); " + chatty.boot
    t0 = time.monotonic()
    reply = chatty.call("hello", run_id=None, timeout_s=60)
    assert reply.ok and time.monotonic() - t0 < 30


def test_receive_and_the_transport_stop_at_their_deadlines(tmp_path):
    data, _ = pack([Entry("tree/a", "file", data=b"x")])
    with pytest.raises(TransferError) as refused:
        receive(data, tmp_path / "r", limits=Limits(timeout_s=0))
    assert refused.value.code == "RECEIVE_TIMEOUT" and not (tmp_path / "r").exists()
    slow = LocalTransport(tmp_path / "armhost")
    slow.boot = "import time; time.sleep(60); " + slow.boot
    t0 = time.monotonic()
    with pytest.raises(TransferError) as refused:
        slow.call("hello", run_id=None, timeout_s=1)
    assert refused.value.code == "TIMEOUT" and time.monotonic() - t0 < 30


@pytest.mark.parametrize("held_out", [False, True])
def test_no_model_arm_or_held_out_cell_is_released_on_an_unestablished_preflight(tmp_path, monkeypatch, held_out):
    monkeypatch.setattr(hidden, "scoring_contained", lambda: True)
    monkeypatch.setattr(campaign, "RELEASED_KINDS", frozenset({"scripted", "raw"}))  # as S8 and S9 will
    secret = tmp_path / "private"
    oracle = make_oracle(secret, "C1")
    case = make_case(tmp_path / "c", "C1", hidden.content_sha256(oracle))
    f = plan_for([case], kind="raw", held_out=("C1",) if held_out else ())
    rec = RecordingTransport(local(tmp_path))
    with pytest.raises(campaign.Refused, match="did not establish corpus isolation"):
        release(f, {"C1": case}, tmp_path, rec, hidden_root=secret)
    assert nothing_registered(tmp_path)
    assert [verb for d, verb, _ in rec.frames if d == "sent"] == ["preflight"]


@pytest.mark.parametrize("checks", [[], [{"name": "mounts", "ok": False, "detail": "a shared folder"}]])
def test_a_preflight_claiming_isolation_without_passing_checks_is_refused(tmp_path, checks):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])

    def claim(verb: str, raw: bytes) -> bytes:
        if verb != "preflight":
            return raw

        def change(message, body):
            message["result"].update(established=True, checks=checks)
            return body
        return rewrite(raw, change)

    with pytest.raises(campaign.Refused, match="without checks that all passed"):
        release(f, {"C1": case}, tmp_path, Hooked(tmp_path / "armhost", after=claim))
    assert nothing_registered(tmp_path)
    assert [e["event"] for e in ReleaseLedger(tmp_path / "ledger", "demo").lines()] == ["preflight_refused"]


def test_a_released_run_is_never_retried_while_its_verdicts_are_provisional(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])

    class Dropping(LocalTransport):
        def exchange(self, request: bytes, *, timeout_s: float, max_reply: int) -> bytes:
            if b'"verb":"run"' in request[:request.index(b"\n")]:
                raise TransferError("TIMEOUT", "the arm host did not answer")
            return super().exchange(request, timeout_s=timeout_s, max_reply=max_reply)

    first = release(f, {"C1": case}, tmp_path, Dropping(tmp_path / "armhost"))
    assert first["validity"]["status"] == "invalid_measurement"
    with pytest.raises(campaign.Refused, match="never retried while its validity verdicts are provisional"):
        release(f, {"C1": case}, tmp_path, local(tmp_path), name="r2", retry_of="demo/r1")
    assert list(AttemptLedger(tmp_path / "ledger", f).attempts()) == ["demo/r1"]


def test_nothing_planted_in_the_work_tree_is_served_followed_or_trusted_by_the_agent(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])
    victim = tmp_path / "victim.txt"
    victim.write_text("untouched\n", encoding="utf-8")
    forged, _ = pack([Entry("tree/calc.py", "file", data=b"forged = True\n")])

    def plant(verb: str, run: Path) -> None:
        if verb != "collect":
            return
        # A forged cache and phase where the agent once kept them, and links where it once wrote its temporary files.
        (run / "collect.tar").write_bytes(forged)
        (run / "collect.json").write_text(json.dumps({"manifest_sha256": "0" * 64, "other": {},
                                                      "other_omitted": 0}), encoding="utf-8")
        (run / "state.json").write_text(json.dumps({"run_id": "demo/r1", "phase": "collected"}), encoding="utf-8")
        for name in ("collect.tar.partial", "state.json.partial", "collect.json.partial"):
            try:
                os.symlink(victim, run / name)
            except OSError:  # Windows without the symlink privilege: a plain file stands in
                (run / name).write_text("planted\n", encoding="utf-8")

    record = release(f, {"C1": case}, tmp_path, Hooked(tmp_path / "armhost", before=plant))
    assert record["validity"]["status"] == "valid", (record["validity"], record["outcome"].get("arm_error"))
    assert (tmp_path / "collected" / "r1" / "tree" / "calc.py").read_text(encoding="utf-8") == FIX["content"]
    assert victim.read_text(encoding="utf-8") == "untouched\n"
    state = tmp_path / "armhost.state" / "runs" / "demo" / "r1"
    assert json.loads((state / "state.json").read_text(encoding="utf-8"))["phase"] == "collected"
    assert (state / "collect.tar").is_file() and (state / "bundle" / "task.json").is_file()
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(state).st_mode) == 0o700
    # A state file that is a link is never read through it.
    if sys.platform != "win32":
        (state / "state.json").unlink()
        os.symlink(victim, state / "state.json")
        with pytest.raises(OSError):
            armhost.read_private(state / "state.json")


def test_concurrent_appends_never_make_verify_report_a_sound_ledger_as_broken(tmp_path):
    import threading

    ledger = ReleaseLedger(tmp_path, "demo")
    errors: list[BaseException] = []

    def writer() -> None:
        try:
            for n in range(150):
                ReleaseLedger(tmp_path, "demo").append(f"demo/r{n}", "preflight", {"n": n})
        except BaseException as exc:  # noqa: BLE001 (reported below)
            errors.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    seen = []
    while thread.is_alive():
        seen.append(ledger.verify())
        ledger.head()
        ledger.lines()
    thread.join(timeout=120)
    assert errors == [] and not thread.is_alive()
    assert all(problems == [] for problems in seen), [p for p in seen if p][:3]
    assert ledger.verify() == [] and len(ledger.lines()) == 150


def test_an_anchor_that_cannot_be_written_never_fails_a_durable_append_and_reads_as_a_lag(tmp_path, monkeypatch):
    from aew_eval import release as release_module

    ledger = ReleaseLedger(tmp_path, "demo")
    ledger.append("demo/r1", "preflight")

    def refused(src, dst):
        raise PermissionError(5, "Access is denied")  # a Windows reader holding the anchor open

    monkeypatch.setattr(release_module.os, "replace", refused)
    monkeypatch.setattr(release_module.time, "sleep", lambda s: None)
    head = ledger.append("demo/r1", "registered")  # durable, so it returns
    monkeypatch.undo()
    assert ledger.head() == head and len(ledger.lines()) == 2
    problems = ledger.verify()
    assert len(problems) == 1 and "lags the chain by one line" in problems[0] and "not a removal" in problems[0]
    ledger.append("demo/r1", "released")  # the next append repairs the anchor
    assert ledger.verify() == []


def test_a_guest_refusal_is_filed_as_the_guests_words_never_as_an_evaluator_fact(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])

    def refuse_run(verb: str, raw: bytes) -> bytes:
        if verb != "run":
            return raw
        return encode_frame({"kind": "reply", "verb": "hello", "ok": False, "result": {},
                             "error": {"code": "TRANSFER_CORRUPT", "message": "guest says: corrupt"}})

    record = release(f, {"C1": case}, tmp_path, Hooked(tmp_path / "armhost", after=refuse_run))
    assert record["validity"]["reason_code"] == "TRANSPORT_ERROR:REQUEST_REFUSED"
    assert "guest says: corrupt" in record["outcome"]["arm_error"] and "error" not in record["outcome"]
    assert campaign.attester("outcome.arm_error") == campaign.GUEST


def test_a_run_reply_that_breaks_the_protocol_files_its_quoted_text_as_the_guests(tmp_path):
    case = make_case(tmp_path / "c", "C1", None)
    f = plan_for([case])

    def malformed_run(verb: str, raw: bytes) -> bytes:
        if verb != "run":
            return raw
        message, _ = decode_frame(raw, what="reply", limits=Limits(), max_payload=Limits().tar_bytes())
        message["result"]["wall_s"] = "GUEST-CHOSEN-TEXT"  # breaks the schema; its error message quotes the value
        return json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

    record = release(f, {"C1": case}, tmp_path, Hooked(tmp_path / "armhost", after=malformed_run))
    assert record["validity"]["reason_code"] == "TRANSPORT_ERROR:REPLY_MALFORMED"
    assert "GUEST-CHOSEN-TEXT" in record["outcome"]["arm_error"] and "error" not in record["outcome"]
    assert campaign.attester("outcome.arm_error") == campaign.GUEST
