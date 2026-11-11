"""`aew init` writes its first configuration before it pins, or nothing (register E119; the designer's ruling of
2026-11-03, §1). The command as an operator runs it; the flags' own rules are in
``tests/unit/test_first_configuration.py``."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

import printed_commands as P
import pytest
import yaml
from conftest import make_git_repo, run_aew
from vertical import ledger as L
from vertical import scripted_operator as S
from vertical.chat import Mailbox

from aew.cli.main import build_parser
from aew.engine.api import Engine
from aew.errors import ValidationFailed
from aew.harness import contract as K
from aew.harness.containment import netns
from aew.util import sha256_file

FILES = {"README.md": "# sample\n"}
GOOD = ["--check-command", "{python} -m pytest -q", "--check-timeout", "60", "--model", "openai/gpt-x"]


def repo(tmp_path: Path) -> Path:
    return make_git_repo(tmp_path / "repo", FILES)


def init(root: Path, *argv: str, env: dict[str, str] | None = None) -> Any:
    return run_aew("-C", str(root), "init", *argv, env=env)


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in (root / ".aew").rglob("*") if p.is_file()}


def test_a_flagged_init_writes_the_files_it_pins_so_no_adopt_or_credential_is_needed(tmp_path):
    root = repo(tmp_path)
    res = init(root, *GOOD)
    assert res.returncode == 0, res.stderr
    out = res.json
    assert out["first_configuration"]["check"] == {"id": "unit", "argv": ["{python}", "-m", "pytest", "-q"],
                                                   "timeout_s": 60}
    assert out["first_configuration"]["provider_env"] == ["OPENAI_API_KEY"]
    assert "aew opencode --acquire --provider-env OPENAI_API_KEY" in out["next"]

    aew = root / ".aew"
    checks = yaml.safe_load((aew / "policy/checks.yaml").read_text(encoding="utf-8"))["checks"]["unit"]
    assert checks["configured"] is True and checks["command"] == ["{python}", "-m", "pytest", "-q"]
    execution = yaml.safe_load((aew / "policy/execution.yaml").read_text(encoding="utf-8"))
    assert execution["configured"] is True and execution["routing"]["default"] == "default"
    # Pinned as written, at revision 0: nothing differs from what was adopted, and nothing asks to configure the check.
    engine = Engine.discover(root)
    state = engine.store.current()
    assert state["revision"] == 0
    for rel in ("policy/checks.yaml", "policy/execution.yaml"):
        assert state["policy_sha256"][rel] == sha256_file(aew / rel)
    actions = run_aew("-C", str(root), "status", "--json").json["next_actions"]
    assert not [a for a in actions if "checks.yaml" in a]
    doctor = run_aew("-C", str(root), "doctor", "--json").json
    lines = {c["check"]: c["status"] for c in doctor["checks"]}
    assert lines["policy:execution"] == "PASS" and lines["model-refs"] == "PASS", doctor
    assert "provider-env" in lines  # nothing looked for the key at init: doctor is what does, in its own environment


def test_a_flag_never_writes_on_a_pinned_project_and_the_integrity_error_stands(tmp_path):
    """Ablation A1's guard: nothing is written after the pin except through adopt and the token."""
    root = repo(tmp_path)
    assert init(root).returncode == 0
    before = tree(root)
    res = init(root, *GOOD)
    assert res.returncode != 0 and res.error["code"] == "INTEGRITY_ERROR"
    assert tree(root) == before
    flagged = repo(tmp_path / "second")
    assert init(flagged, *GOOD).returncode == 0
    before = tree(flagged)
    res = init(flagged, "--model", "anthropic/other")
    assert res.error["code"] == "INTEGRITY_ERROR" and tree(flagged) == before
    assert "aew lead acquire" in res.error["message"] and "aew manifest adopt" in res.error["message"]  # F8


def actions(root: Path) -> list[str]:
    return run_aew("-C", str(root), "status", "--json").json["next_actions"]


def test_the_route_a_note_prints_after_the_pin_runs_as_printed(tmp_path):
    """Review of #329, F1: the first step of what a successful init prints isn't refused. (The provider note that
    first carried it is gone: opencode needs its key like any provider, the operator's decision of 2026-11-06; the
    route is the one `next` prints for what is still missing.)"""
    root = repo(tmp_path)
    res = init(root, "--model", "opencode/big")
    assert "provider_note" not in res.json["first_configuration"]
    command, fenced = P.commands(res.json["next"])[0]
    assert not fenced and command == "aew lead acquire --expect-rev 0"
    assert run_aew("-C", str(root), *shlex.split(command)[1:]).returncode == 0


def test_a_fresh_init_with_an_opencode_model_names_its_key_and_a_launch_passes_only_with_it_set(tmp_path):
    """E119's first configuration names opencode's key variable, as for every known provider (the operator,
    2026-11-06): the pinned policy's provider_env carries it, and the launch predicate passes with it set and refuses
    without it. The key is synthetic."""
    root = repo(tmp_path)
    res = init(root, "--model", "opencode/x")
    assert res.returncode == 0, res.stdout
    variable = netns.PROVIDER_KEY_ENV["opencode"]
    assert variable == "OPENCODE_API_KEY" and res.json["first_configuration"]["provider_env"] == [variable]
    policy = yaml.safe_load((root / ".aew" / "policy" / "execution.yaml").read_text(encoding="utf-8"))
    assert policy["provider_env"] == [variable]
    assert policy["profiles"]["default"] == {"model": "opencode/x"}
    for env, want in (({variable: "synthetic-not-a-key"}, None), ({}, variable), ({variable: ""}, variable)):
        assert netns.provider_key_missing("opencode", policy["provider_env"], env, on_relay_route=True) == want, env


def test_resume_gives_a_vacant_seat_the_one_text_status_does(tmp_path):
    """Review of #329, F3: `aew resume` named the credential route alone, and following it refuses the `--acquire` that
    `next` named."""
    root = repo(tmp_path)
    assert init(root, *GOOD).returncode == 0
    resume = run_aew("-C", str(root), "resume").stdout
    words = " ".join(resume.split())
    assert "No Lead holds authority: `aew opencode --acquire` takes it" in words
    assert " ".join(K.HELD_SEAT.split()) in words
    assert [a for a in actions(root) if a.startswith("no Lead holds the seat:") and K.HELD_SEAT in a]


def test_the_way_back_the_classification_route_names_gives_acquire_the_seat_again(tmp_path):
    """Review of #329, F2: classified as the action says, the seat is held and taking it is refused; the release that
    the action names leaves it vacant, and it can be taken again. Each `--acquire` takes the seat through
    `Engine.lead_acquire` (`lead_broker`, `opencode/lead.py`), so this takes it the same way, through `aew lead
    acquire`: under `required`, Linux's default, a Lead session started here is refused for containment before it
    reaches the seat, and `aew opencode` would start OpenCode."""
    root = repo(tmp_path)
    assert init(root, *GOOD).returncode == 0
    classify = [a for a in actions(root) if a.startswith("classify authority candidates")]
    assert classify and f"aew lead release {K.EXPECT_REV}" in classify[0]
    token = run_aew("-C", str(root), "lead", "acquire", "--expect-rev", "0").json["token"]
    env = {"AEW_LEAD_TOKEN": token}
    accepted = run_aew("-C", str(root), "authority", "accept", "C-001", "--class", "orientation", "--expect-rev", "1",
                       env=env)
    assert accepted.returncode == 0, accepted.stderr
    take = ("-C", str(root), "lead", "acquire", "--expect-rev", "2")
    held = run_aew(*take)
    assert held.returncode != 0 and held.error["code"] == "PERMISSION_DENIED", held.stderr
    released = run_aew("-C", str(root), "lead", "release", "--expect-rev", "2", env=env)
    assert released.returncode == 0, released.stderr
    assert run_aew("-C", str(root), "status", "--json").json["lead"]["status"] == "vacant"
    again = run_aew(*take[:-1], "3")
    assert again.returncode == 0, again.stderr


def test_an_interrupted_init_may_run_again_with_other_values(tmp_path):
    root = repo(tmp_path)
    assert init(root, *GOOD).returncode == 0
    (root / ".aew/state/control.yaml").unlink()  # the commit point never happened
    res = init(root, "--check-command", "make test", "--model", "opencode/big")
    assert res.returncode == 0, res.stderr
    assert yaml.safe_load((root / ".aew/policy/execution.yaml").read_text(encoding="utf-8"))["provider_env"] == [
        "OPENCODE_API_KEY"]
    state = Engine.discover(root).store.current()
    assert state["policy_sha256"]["policy/checks.yaml"] == sha256_file(root / ".aew/policy/checks.yaml")


@pytest.mark.parametrize(("argv", "code", "reason"), [
    (["--check-command", ""], "USAGE", "check_command_empty"),
    (["--check-command", "make && make lint"], "USAGE", "check_command_shell"),
    (["--check-command", "FOO=1 make"], "USAGE", "check_command_shell"),
    (["--check-command", r"C:\py\python -m pytest"], "USAGE", "check_command_backslash"),
    (["--check-command", "make 'x"], "USAGE", "check_command_unparseable"),
    (["--check-timeout", "30"], "USAGE", "check_timeout_alone"),
    (["--provider", "openai"], "USAGE", "provider_alone"),
    (["--model", "fakeprov/m"], "USAGE", "unknown_provider"),
    (["--model", "bare"], "VALIDATION_FAILED", "model_id_no_provider"),
])
def test_a_refused_flag_writes_nothing(tmp_path, argv, code, reason):
    """Ablation A2: a refused command written anyway."""
    root = repo(tmp_path)
    res = init(root, *argv)
    assert res.returncode != 0 and res.error["code"] == code, res.stderr
    assert res.error["details"]["reason"] == reason
    assert not (root / ".aew").exists()


@pytest.mark.parametrize("timeout", ["0", "-5"])
def test_the_bytes_are_checked_before_the_pin_and_a_refusal_writes_nothing(tmp_path, timeout):
    """Ablation A7: `check_policy_bytes` skipped. The schema's rule refuses a timeout not above zero, which the flag's
    own parser leaves to it, so only the check on the bytes stops this one."""
    root = repo(tmp_path)
    res = init(root, "--check-command", "make", "--check-timeout", timeout)
    assert res.returncode != 0 and res.error["code"] == "VALIDATION_FAILED", res.stderr
    assert not (root / ".aew").exists()


def test_flagless_init_names_both_missing_settings_and_orders_the_route(tmp_path):
    """The pin's bytes are covered by the goldens in `test_coordination_store`."""
    root = repo(tmp_path)
    out = init(root).json
    guidance = out["next"]
    assert "no check command or model" in guidance
    assert ".aew/policy/checks.yaml" in guidance and ".aew/policy/execution.yaml" in guidance
    assert K.HELD_SEAT in guidance
    assert guidance.endswith("Then start the Lead with `aew opencode --acquire`")
    assert [command for command, _ in P.commands(guidance)] == [
        "aew lead acquire --expect-rev 0",
        K.MANIFEST_ADOPT.strip("`"),
        "aew opencode --acquire",  # the held-seat warning
        f"aew lead release {K.EXPECT_REV}",
        "aew opencode --acquire",
    ]
    for command, fenced in P.commands(guidance):
        P.parse(command, fenced=fenced)
    assert "first_configuration" not in out
    # `tools`: the tools AEW brings, as the operator chose them (aew.capability.consent), in a key of its own
    # `map`: the first structural map, generated and selected by init (register E184), or the line saying why not
    assert sorted(out) == ["aew_root", "authority_candidates", "map", "next", "ok", "project_id", "provider_key",
                           "revision", "tools"]
    # the first-use line (the operator's decision of 2026-11-06): a provider key and a paid model, no free models
    assert "AEW needs a provider key" in out["provider_key"] and "https://opencode.ai/docs/zen/" in out["provider_key"]


def test_a_flag_is_refused_under_the_lead_broker_and_writes_nothing(tmp_path):
    """Ablation A4. The refusal comes before anything runs, from the one reachability check."""
    root = repo(tmp_path)
    res = init(root, "--model", "openai/m", env={"AEW_LEAD_BROKER": "unused"})
    assert res.returncode != 0 and res.error["code"] == "USAGE" and "ask the operator" in res.error["message"]
    assert not (root / ".aew").exists()


# ---------------------------------------------------------------------------------------------- the driver's hook


def operator(tmp_path: Path) -> S.Operator:
    lab = S.new_world(tmp_path)
    return S.Operator(lab, L.Ledger("unit"), tmp_path, Mailbox(tmp_path / "sync" / "chat", "operator"))


def test_the_operators_recorded_line_parses_and_what_it_typed_is_what_ran(tmp_path):
    """The driver enters through `aew.cli.main`: its line, recorded exactly, parses with `build_parser()` to the values
    the driver gave, and no fixture is in it."""
    op = operator(tmp_path)
    check = ["{python}", "-c", "print('it''s')", "x y"]
    argv = ["--check-command", shlex.join(check), "--model", S.OFFLINE_MODEL]
    res = op.first_configuration(argv, S.world_fixtures(op.lab), {S.OFFLINE_PROVIDER: S.OFFLINE_KEY})
    assert res.returncode == 0, res.stderr
    assert f"aew opencode --acquire --provider-env {S.OFFLINE_KEY}" in res.json["next"]
    (typed,) = [t for t in op.transcript if t["step"] == "init"]
    words = shlex.split(typed["input"])
    assert words[0] == "aew"
    parsed: argparse.Namespace = build_parser().parse_args(words[1:])
    assert parsed.command == "init" and parsed.check_command == shlex.join(check) and parsed.model == S.OFFLINE_MODEL
    assert shlex.split(parsed.check_command) == check
    for fixture in ("harness", "writable", "containment", "crawl", "steering", "notify"):
        assert fixture not in typed["input"]
    written = yaml.safe_load((op.root / ".aew/policy/checks.yaml").read_text(encoding="utf-8"))
    assert written["checks"]["unit"]["command"] == check


def test_the_recorded_line_reads_as_an_operator_would_type_it(tmp_path):
    """`{python}` stays bare, and the driver's check commands, with their own quotes and backslash, still split back."""
    op = operator(tmp_path)
    line = S.check_line(["{python}", "-m", "pytest", "-q", "tests"])
    assert line == "{python} -m pytest -q tests"
    res = op.first_configuration(["--check-command", line, "--model", S.OFFLINE_MODEL], S.world_fixtures(op.lab),
                                 {S.OFFLINE_PROVIDER: S.OFFLINE_KEY})
    assert res.returncode == 0, res.stderr
    (typed,) = [t for t in op.transcript if t["step"] == "init"]
    assert typed["input"] == f"aew init --check-command '{line}' --model {S.OFFLINE_MODEL}"
    for argv in (["{python}", "-c", r"p.write_text(p.read_text() + 'built\n')"],
                 ["{python}", "-c", "open('check-output.txt', 'w').write('x')"]):
        assert shlex.split(S.check_line(argv)) == argv


def test_each_fixture_is_recorded_not_counted_and_pinned_by_the_real_path(tmp_path):
    op = operator(tmp_path)
    fixtures = S.world_fixtures(op.lab, steering="crawl")
    res = op.first_configuration(["--check-command", "make", "--model", S.OFFLINE_MODEL], fixtures,
                                 {S.OFFLINE_PROVIDER: S.OFFLINE_KEY})
    assert res.returncode == 0, res.stderr
    recorded = {o["fixture"] for o in op.ledger.observations if o["kind"] == "setup_fixture"}
    assert recorded == {"harness: fake", "containment.writable", "steering.mode",
                        f"known provider {S.OFFLINE_PROVIDER}"}
    assert set(op.ledger.counts().values()) == {0}, op.ledger.counts()
    execution = op.root / ".aew/policy/execution.yaml"
    doc = yaml.safe_load(execution.read_text(encoding="utf-8"))
    assert doc["harness"] == "fake" and doc["steering"] == {"mode": "crawl"}
    assert doc["profiles"] == {"default": {"model": S.OFFLINE_MODEL}}  # what the operator typed is left as typed
    assert Engine.discover(op.root).store.current()["policy_sha256"]["policy/execution.yaml"] == sha256_file(execution)


def test_a_fixture_is_checked_with_the_bytes_it_changes(tmp_path):
    """The hook pins nothing itself: a fixture the policy refuses is refused by the real path, with nothing written."""
    op = operator(tmp_path)

    def bad(doc: dict[str, Any]) -> None:
        doc["harness"] = ""

    res = op.first_configuration(["--check-command", "make", "--model", S.OFFLINE_MODEL], {"bad": bad},
                                 {S.OFFLINE_PROVIDER: S.OFFLINE_KEY})
    assert res.returncode != 0 and ValidationFailed.code in res.stderr
    assert not (op.root / ".aew").exists()


def test_the_hook_leaves_nothing_behind_and_a_fake_provider_is_unknown_outside_it(tmp_path):
    """Nothing an installed `aew` can reach: the tables and `Engine.initialize` are as they were once the hook is done,
    and on the operator's own command line the fake providers are refused."""
    op = operator(tmp_path)
    tables = dict(netns.PROVIDER_KEY_ENV), netns.CATALOG_ADDRESSED
    initialize = Engine.__dict__["initialize"]
    known = {"vuatprov": "VUAT_PROVIDER_KEY", S.OFFLINE_PROVIDER: S.OFFLINE_KEY}
    res = op.first_configuration(["--check-command", "make", "--model", "vuatprov/m"], S.world_fixtures(op.lab), known)
    assert res.returncode == 0, res.stderr
    assert "aew opencode --acquire --provider-env VUAT_PROVIDER_KEY" in res.json["next"]
    assert (dict(netns.PROVIDER_KEY_ENV), netns.CATALOG_ADDRESSED) == tables
    assert Engine.__dict__["initialize"] is initialize
    assert S.OFFLINE_PROVIDER not in netns.PROVIDER_KEY_ENV and "vuatprov" not in netns.PROVIDER_KEY_ENV
    outside = repo(tmp_path / "plain")
    assert init(outside, "--model", S.OFFLINE_MODEL).error["details"]["reason"] == "unknown_provider"


def test_no_source_file_names_a_driver_fixture():
    """The invariant's other half: the product holds no hook, table entry or variable for the driver's world."""
    src = Path(__file__).resolve().parents[2] / "src" / "aew"
    words = ("fakeprov", "vuatprov", "world_around_init", "setup_fixture")
    found = [(p.name, w) for p in src.rglob("*.py") for w in words if w in p.read_text(encoding="utf-8")]
    assert found == []
