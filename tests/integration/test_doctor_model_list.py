"""`aew doctor` reads the harness's model list by default, as a launch reads it, and names a pinned model the list does
not offer, with the ones its provider does list (register E153; the designer's ruling (a), relayed 2026-11-07). The
fake V2 server stands in for OpenCode; synthetic providers and ids only."""

from __future__ import annotations

from typing import Any

import pytest
from fake_harness import HarnessLab
from harness_conformance import FakeOpenCodeDriver

from aew.harness import model_list, runlog
from aew.util import dump_yaml, load_yaml

LISTED = [{"id": "fake-model", "providerID": "fakeprov", "enabled": True, "variants": [{"id": "high"}]},
          {"id": "other-model", "providerID": "fakeprov", "enabled": True, "variants": [{"id": "high"}]}]
ELSEWHERE = [{"id": "cheaper-model", "providerID": "other", "enabled": True, "variants": []}]


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    lab.env["AEW_OPENCODE_CATALOG_SETTLE_S"] = "1"  # a catalog that never lists the pin settles quickly here
    try:
        yield lab
    finally:
        lab.cleanup()


def serve(lab: HarnessLab, models: list[dict[str, Any]], **knobs: Any) -> None:
    lab.script("default", {"steps": [], "server": {"models": models, **knobs}})


def doctor(lab: HarnessLab, *args: str, env: dict[str, str] | None = None) -> tuple[int, dict[str, str] | None]:
    res = lab.aew("doctor", "--json", *args, env=env)
    rows = {c["check"]: c for c in res.json["checks"]}
    return res.returncode, rows.get(model_list.CHECK)


def set_model(lab: HarnessLab, model: str) -> None:
    path = lab.aew_root / "policy/execution.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    for profile in policy["profiles"].values():
        profile["model"] = model
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    lab.project.pin_policy()


def leftovers(lab: HarnessLab) -> list[str]:
    parent = runlog.run_dir(lab.aew_root, "x").parent
    return sorted(d.name for d in parent.iterdir()) if parent.is_dir() else []


def test_a_pinned_model_the_list_does_not_offer_is_a_fail_naming_it_and_what_its_provider_lists(lab):
    serve(lab, LISTED)
    set_model(lab, "missing-model")
    code, row = doctor(lab)
    assert code == 1 and row is not None and row["status"] == "FAIL", row
    assert "fakeprov/missing-model is not in opencode" in row["detail"], row
    assert "fakeprov lists fakeprov/fake-model, fakeprov/other-model" in row["detail"], row
    assert "Set profiles.standard.model to a model it lists, such as fakeprov/fake-model" in row["detail"], row
    # Read as a launch reads it, and gone after: no run, no directory, nothing left running in the lab's tree.
    assert leftovers(lab) == [], leftovers(lab)


def test_a_listed_model_passes_and_the_list_is_read_once_until_refresh(lab):
    serve(lab, LISTED)
    code, row = doctor(lab)
    assert code == 0 and row is not None and row["status"] == "PASS", row
    assert row["detail"].startswith("profile standard: fakeprov/fake-model is in opencode"), row
    assert "(read just now)" in row["detail"], row
    serve(lab, ELSEWHERE)  # the cached list answers: the server is not asked again
    _, again = doctor(lab)
    assert again is not None and again["status"] == "PASS" and "cached: `aew doctor --refresh` reads it again" in \
        again["detail"], again
    _, fresh = doctor(lab, "--refresh")
    assert fresh is not None and fresh["status"] == "FAIL", fresh
    assert "it lists no model of fakeprov; the providers it lists are other" in fresh["detail"], fresh


def test_a_changed_projection_is_read_again_not_answered_from_the_cache(lab):
    serve(lab, LISTED)
    assert doctor(lab)[1]["status"] == "PASS"
    set_model(lab, "other-model")  # another pin, so another projected configuration
    _, row = doctor(lab)
    assert row is not None and row["status"] == "PASS" and "fakeprov/other-model" in row["detail"], row
    assert "(read just now)" in row["detail"], row


def test_a_disabled_model_and_a_missing_variant_are_fails_with_their_fix(lab):
    serve(lab, [{**LISTED[0], "enabled": False}])
    _, row = doctor(lab)
    assert row is not None and row["status"] == "FAIL" and "is disabled in opencode" in row["detail"], row
    serve(lab, [{**LISTED[0], "variants": [{"id": "low"}]}])
    _, row = doctor(lab, "--refresh")
    assert row is not None and row["status"] == "FAIL", row
    assert "has no variant 'high' (the profile's effort)" in row["detail"] and "it offers low" in row["detail"], row


def test_a_read_that_outlasts_the_launchs_start_deadline_is_a_fail_with_its_fix_and_leaves_nothing(lab):
    serve(lab, LISTED, catalog_delay_s=60)
    code, row = doctor(lab, env={"AEW_RUN_START_S": "4"})
    assert code == 1 and row is not None and row["status"] == "FAIL", row
    assert "was not read within 4s, a launch's own start deadline (AEW_RUN_START_S)" in row["detail"], row
    assert "then run `aew doctor --refresh`" in row["detail"], row
    assert leftovers(lab) == [], leftovers(lab)
    assert not (lab.aew_root / model_list.CACHE_REL).exists()  # an unfinished read is never cached


def test_without_a_harness_binary_the_list_is_not_read_and_nothing_fails_on_it(lab, tmp_path):
    code, row = doctor(lab, env={"AEW_OPENCODE_BIN": str(tmp_path / "no-such-opencode")})
    assert row is not None and row["status"] == "WARN", row
    assert row["detail"].startswith("the model list was not read: profile standard: no harness binary"), row
