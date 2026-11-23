"""`aew doctor` reads the harness's model list by default, as a launch reads it, and names a pinned model the list does
not offer, with the ones its provider does list (register E153; the designer's ruling (a), relayed 2026-11-07). The
fake V2 server stands in for OpenCode; synthetic providers and ids only."""

from __future__ import annotations

import hashlib
import sys
from typing import Any

import pytest
from fake_harness import HarnessLab
from harness_conformance import FakeOpenCodeDriver
from lead_session import synthetic_home

from aew.harness import model_list, runlog
from aew.util import dump_yaml, load_yaml

LISTED = [{"id": "fake-model", "providerID": "fakeprov", "enabled": True, "variants": [{"id": "high"}]},
          {"id": "other-model", "providerID": "fakeprov", "enabled": True, "variants": [{"id": "high"}]}]
ELSEWHERE = [{"id": "cheaper-model", "providerID": "other", "enabled": True, "variants": []}]


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    lab.env["OPENCODE_DB"] = str(tmp_path / "no-host-login.db")
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


def edit_policy(lab: HarnessLab, change: Any) -> None:
    path = lab.aew_root / "policy/execution.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    change(policy)
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    lab.project.pin_policy()


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


def test_doctor_refuses_a_free_zen_pin_even_with_an_export(lab):
    def configure(policy):
        policy["provider_env"] = ["OPENCODE_API_KEY"]
        policy["containment"]["network"]["upstreams"]["opencode"] = lab.provider.url
        for profile in policy["profiles"].values():
            profile.update(provider="opencode", model="synthetic-free")
            profile.pop("effort", None)

    edit_policy(lab, configure)
    serve(lab, [{"id": "synthetic-free", "providerID": "opencode", "enabled": True, "variants": [],
                 "cost": [{"input": 0, "output": 0}]}])
    code, row = doctor(lab, env={"OPENCODE_API_KEY": "SYNTHETIC-NOT-A-KEY"})
    assert code == 1 and row is not None and row["status"] == "FAIL", row
    assert "verified paid base price" in row["detail"]
    assert "dispatch a new invocation with --profile or --model" in row["detail"]


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
    first = lab.aew("doctor", "--json")
    # The default doctor may wait for the harness: it says so first, on stderr (review of #367, F5).
    assert "aew doctor: reading opencode's model list for fakeprov/fake-model as a launch reads it" in first.stderr
    assert "the list is cached, and `aew doctor --refresh` reads it again" in first.stderr, first.stderr
    code, row = first.returncode, {c["check"]: c for c in first.json["checks"]}.get(model_list.CHECK)
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


def test_a_catalog_that_offers_nothing_in_time_is_never_an_answer_about_the_model_and_is_not_cached(lab):
    """Review of #367, F1: an unreachable catalog settles empty, as a launch's wait does; a launch refuses that as
    timing-dependent (CATALOG_TIMEOUT), never as a lasting incompatibility, so doctor neither blames the pinned model
    nor caches it: once the catalog is back, the next plain doctor reads it again and passes."""
    serve(lab, LISTED, catalog_delay_s=600)
    code, row = doctor(lab, env={"AEW_OPENCODE_CATALOG_S": "2"})
    assert code == 1 and row is not None and row["status"] == "FAIL", row
    assert "opencode offered no model at all within its catalog wait" in row["detail"], row
    assert "never a lasting answer about the pinned model" in row["detail"], row
    assert "Check the network the execution policy allows for the harness's model catalog" in row["detail"], row
    assert "Set profiles." not in row["detail"], row
    assert not (lab.aew_root / model_list.CACHE_REL).exists()
    serve(lab, LISTED)
    _, again = doctor(lab)
    assert again is not None and again["status"] == "PASS" and "(read just now)" in again["detail"], again


def test_two_profiles_on_a_catalog_that_offers_nothing_wait_for_it_once(lab):
    """Review of #367, N2: each would wait out the catalog (about 90 s by default) for an answer that does not depend on
    its model. Both are named, and the second points at the first."""
    edit_policy(lab, lambda policy: policy["profiles"].update(
        {"second": {**next(iter(policy["profiles"].values())), "model": "other-model"}}))
    serve(lab, LISTED, catalog_delay_s=600)
    res = lab.aew("doctor", "--json", env={"AEW_OPENCODE_CATALOG_S": "2"})
    row = next(c for c in res.json["checks"] if c["check"] == model_list.CHECK)
    assert row["status"] == "FAIL", row
    assert res.stderr.count("reading opencode's model list") == 1, res.stderr
    first = next(n for n in sorted(load_yaml((lab.aew_root / "policy/execution.yaml").read_text(encoding="utf-8"))
                                   ["profiles"]))
    assert f"the same harness and provider as profile {first}, not waited for again" in row["detail"], row
    assert "opencode offered no model at all within its catalog wait" in row["detail"], row


def test_two_profiles_wait_once_when_the_start_deadline_ends_the_read_before_the_catalog_wait(lab):
    """Review of E137, F3: waiting once holds whatever ended the wait."""
    edit_policy(lab, lambda policy: policy["profiles"].update(
        {"second": {**next(iter(policy["profiles"].values())), "model": "other-model"}}))
    serve(lab, LISTED, catalog_delay_s=600)
    res = lab.aew("doctor", "--json", env={"AEW_RUN_START_S": "4"})
    row = next(c for c in res.json["checks"] if c["check"] == model_list.CHECK)
    assert row["status"] == "FAIL" and "was not read within 4s" in row["detail"], row
    assert res.stderr.count("reading opencode's model list") == 1, res.stderr
    assert "not waited for again" in row["detail"], row


def test_a_start_deadline_that_ends_before_the_server_starts_is_the_deadline_row_and_is_waited_for_once(lab):
    """The deadline counts from before the containment, as a launch's does, so on a slow host it can end before the
    server starts: that is the start deadline running out, not a harness that failed to start, and the read is
    neither cached nor waited for again. A zero deadline ends it there every time."""
    edit_policy(lab, lambda policy: policy["profiles"].update(
        {"second": {**next(iter(policy["profiles"].values())), "model": "other-model"}}))
    serve(lab, LISTED)
    res = lab.aew("doctor", "--json", env={"AEW_RUN_START_S": "0"})
    row = next(c for c in res.json["checks"] if c["check"] == model_list.CHECK)
    assert row["status"] == "FAIL", row
    assert "was not read within 0s, a launch's own start deadline (AEW_RUN_START_S)" in row["detail"], row
    assert "did not start as a launch starts it" not in row["detail"], row
    assert "(what ended it: no time was left to start the OpenCode server)" in row["detail"], row
    assert "had not started by then, so raise AEW_RUN_START_S" in row["detail"], row
    assert "the harness's model catalog" not in row["detail"], row  # no server: its catalog is not the cause
    assert "not waited for again" in row["detail"], row
    assert res.stderr.count("reading opencode's model list") == 1, res.stderr
    assert leftovers(lab) == [], leftovers(lab)
    assert not (lab.aew_root / model_list.CACHE_REL).exists()


def test_a_profile_with_a_cached_list_gets_its_answer_after_another_profile_waited_for_nothing(lab):
    """Review of E137, F4: the wait it skips is not one a cached answer would have made."""
    serve(lab, LISTED)
    code, row = doctor(lab)  # caches the list of the one profile the policy has, which sorts after the new one
    assert code == 0 and row is not None and row["status"] == "PASS", row
    edit_policy(lab, lambda policy: policy["profiles"].update(
        {"afirst": {**next(iter(policy["profiles"].values())), "model": "other-model"}}))
    serve(lab, LISTED, catalog_delay_s=600)
    res = lab.aew("doctor", "--json", env={"AEW_OPENCODE_CATALOG_S": "2"})
    row = next(c for c in res.json["checks"] if c["check"] == model_list.CHECK)
    assert res.stderr.count("reading opencode's model list") == 1, res.stderr
    assert "profile afirst: opencode offered no model at all" in row["detail"], row
    assert "not waited for again" not in row["detail"], row  # the other answered from its cached list, and passes


def test_no_provider_value_reaches_doctors_output_or_any_file_it_leaves(lab):
    """Review of #367, F6: the read runs with the launch's environment, so a provider variable's value reaches its
    server as a launch's does, and never doctor's output, its cache or any other file under the project's .aew."""
    secret = "aewtest-synthetic-provider-value-7f3e9c2b"
    lab.env["AEWTEST_PROVIDER_KEY"] = secret
    edit_policy(lab, lambda doc: doc.update(provider_env=["AEWTEST_PROVIDER_KEY"]))
    serve(lab, LISTED)
    res = lab.aew("doctor", "--json")
    assert {c["check"]: c for c in res.json["checks"]}[model_list.CHECK]["status"] == "PASS"
    assert secret not in res.stdout + res.stderr
    leaked = [str(p) for p in lab.aew_root.rglob("*") if p.is_file() and secret.encode() in p.read_bytes()]
    assert leaked == [], leaked
    assert leftovers(lab) == [], leftovers(lab)


def test_a_sandbox_that_cannot_be_established_here_is_a_warn_and_leaves_nothing(lab):
    """Review of #367, F6: where a launch's containment is not established here (an egress allowlist entry that is not
    host:port, which the launch refuses the same way, before any sandbox), the list is not read: a WARN naming why,
    and no directory, run or process left."""
    edit_policy(lab, lambda doc: doc["containment"]["network"].update(egress_allow=["not a host"]))
    serve(lab, LISTED)
    _, row = doctor(lab)
    assert row is not None and row["status"] == "WARN", row
    assert "a launch's containment was not established here" in row["detail"], row
    assert "egress_allow" in row["detail"], row
    assert leftovers(lab) == [], leftovers(lab)


def test_a_provider_key_a_launch_would_not_get_is_named_as_the_launchs_refusal(lab):
    """Review of #367, F4: on the relay route (Linux) a profile whose provider would get no key is refused at launch
    (provider_key_missing), so doctor's row is red and says so, not that containment failed. Off it there is no relay
    and nothing to judge, and the list is read as before."""
    lab.env.pop("OPENAI_API_KEY", None)
    edit_policy(lab, lambda doc: doc["profiles"].update(standard={"provider": "openai", "model": "gpt-test"}))
    serve(lab, [{"id": "gpt-test", "providerID": "openai", "enabled": True, "variants": []}])
    _, row = doctor(lab, env={"OPENAI_API_KEY": ""})
    assert row is not None, row
    if not sys.platform.startswith("linux"):
        assert "provider_key_missing" not in row["detail"], row
        return
    assert row["status"] == "FAIL" and "a launch would be refused (provider_key_missing)" in row["detail"], row
    assert "containment was not established" not in row["detail"], row


@pytest.mark.parametrize("route", ["default Lead", "worker profile"])
def test_live_models_request_uses_the_launchs_login_even_with_a_cached_catalog(lab, tmp_path, route):
    saved, exported = "synthetic-saved-login", "synthetic-worker-export"
    saved_hash, export_hash = (hashlib.sha256(value.encode()).hexdigest() for value in (saved, exported))
    home = synthetic_home(tmp_path / "operator", {"openai": saved})
    lab.env.update(OPENCODE_DB=str(home / ".local/share/opencode/opencode.db"), OPENAI_API_KEY=exported)

    def configure(policy):
        if route == "default Lead":
            policy["containment"]["mode"] = "allow_weaker"
        policy["containment"]["network"]["upstreams"]["openai"] = lab.provider.url
        policy["profiles"]["standard"] = {"provider": "openai", "model": "listed-model"}

    edit_policy(lab, configure)
    serve(lab, [{"id": "listed-model", "providerID": "openai", "family": "synthetic", "enabled": True}])
    first = lab.aew("doctor", "--json")
    rows = [r for r in first.json["checks"] if r["check"] == "provider-relay"]
    if not sys.platform.startswith("linux"):
        assert lab.provider.model_requests == [] and rows and all(r["status"] == "WARN" for r in rows)
        return
    tested = saved_hash if route == "default Lead" else export_hash
    source = "saved OpenCode API key" if route == "default Lead" else "environment"
    passed = next(r for r in rows if r["detail"].startswith(route))
    assert passed["status"] == "PASS" and "provider answered HTTP 200" in passed["detail"]
    assert source in passed["detail"] and lab.provider.model_requests.count(("/v1/models", tested)) == 1
    assert (lab.aew_root / model_list.CACHE_REL).is_file()

    kept = leftovers(lab)  # a weaker catalog read can retain its register marker
    lab.provider.models_status[tested] = 401
    for args in (("--json",), ()):
        response = lab.aew("doctor", *args)
        assert response.returncode == 1
        if args:
            failed = next(r for r in response.json["checks"] if r["check"] == "provider-relay"
                          and r["detail"].startswith(route))
            assert failed["status"] == "FAIL" and "provider answered HTTP 401" in failed["detail"]
            assert source in failed["detail"]
        else:
            line = next(line for line in response.stdout.splitlines() if "provider-relay" in line and route in line)
            assert "FAIL" in line and "provider answered HTTP 401" in line
        assert "cached" in response.stdout
        assert all(v not in response.stdout + response.stderr for v in (
            saved, exported, "X-Private-Probe-Header", "upstream-private-value", "private-provider-error",
            "Authorization:", "aew-relay-"))
    assert lab.provider.model_requests.count(("/v1/models", tested)) == 3

    lab.provider.models_status[tested] = 0  # upstream closes before replying
    unavailable = lab.aew("doctor", "--json")
    row = next(r for r in unavailable.json["checks"] if r["check"] == "provider-relay"
               and r["detail"].startswith(route))
    assert row["status"] == "WARN" and "relay answered HTTP 502" in row["detail"]
    assert lab.provider.model_requests.count(("/v1/models", tested)) == 4 and leftovers(lab) == kept

    sent = list(lab.provider.model_requests)
    edit_policy(lab, lambda p: p["containment"]["network"].update(mode="isolated"))
    offline = lab.aew("doctor", "--json")
    [skipped] = [r for r in offline.json["checks"] if r["check"] == "provider-relay"]
    assert skipped["status"] == "WARN" and "no provider relay" in skipped["detail"]
    assert lab.provider.model_requests == sent
