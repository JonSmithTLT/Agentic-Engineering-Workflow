"""Pins for the companion alpha verdict over the vertical's saved evidence."""
from vertical import alpha, ledger
from vertical import report as R


def measured_scenarios():
    scenarios = {name: ledger.Ledger(name, platform="linux") for name in (*alpha.LIMIT_PROBES, *alpha.PREFLIGHT)}
    for name, limits in alpha.LIMIT_PROBES.items():
        for limit in limits:
            scenarios[name].hard_limit(limit, ledger.HELD)
    for name in (alpha.FRESH, alpha.FORCED):
        scenarios[name].observe(ledger.RESULT_REACHED, reached=True, asked=True, problems=[])
    fresh = scenarios[alpha.FRESH]
    for decision in ledger.V1_DECISIONS:
        fresh.decision(decision, "", label=decision, asked_by="Lead")
    fresh.steps = [
        {"key": "open", "step": 3, "state": "not built", "held_by": ["G3"]},
        {"key": "publish", "step": 7, "state": "not built", "held_by": ["G3", "I4-06", "I4-B7"]},
        {"key": "ask", "step": 4, "state": "not built", "held_by": ["G30"]},
    ]
    return scenarios


def render(scenarios, *, platform="linux"):
    rows = [{"ledger": led.to_json(), "outcome": R.PASSED if name in alpha.PREFLIGHT else R.FAILED}
            for name, led in scenarios.items()]
    return alpha.summary(rows, platform=platform, strict_pass=R.PASSED)


def test_non_g3_and_unkeyed_fallbacks_still_fail():
    scenarios = measured_scenarios()
    fresh = scenarios[alpha.FRESH]
    fresh.observe("fallback", step="ask", oracle_key="ask", observed="held by G3")
    fresh.observe("fallback", step="caches", observed="held by G3")
    fresh.observe("fallback", step="reopen:acquire", observed="held by G3")
    text = render(scenarios)
    assert "Alpha scripted gate: FAIL" in text
    for name in ("ask", "caches", "reopen:acquire"):
        assert f"Unexcused fallback: {name}" in text


def test_g3_and_mixed_fallbacks_are_excused_and_printed():
    scenarios = measured_scenarios()
    fresh = scenarios[alpha.FRESH]
    fresh.observe("fallback", step="open", oracle_key="open")
    fresh.observe("fallback", step="answer:publish", oracle_key="publish")
    fresh.observe("fallback", step="answer:publish", oracle_key="publish")
    fresh.count("refusals", {}, actor="lead", step="open")
    names = ("Excused G3 fallback: open (step 3 open; held by G3)",
             "Excused G3 fallback: answer:publish (step 7 publish; held by G3, I4-06, I4-B7)")
    passed = render(scenarios)
    assert "Alpha scripted gate: PASS" in passed
    assert "operator fallbacks: open, answer:publish, answer:publish" in fresh.summary()
    assert "refusals 1" in fresh.summary()
    fresh.count("seat_operations", {}, actor="operator", step="open")
    fresh.decision("extra", "", label="accept_verification", asked_by="Lead")
    scenarios["V1-evidence-mismatch"].hard_limit("evidence_mismatch", ledger.UNNAMED)
    scenarios[alpha.FORCED].observations.clear()
    failed = render(scenarios, platform="win32")
    assert failed.startswith(ledger.WINDOWS_UNQUALIFIED)
    assert "Alpha scripted gate: FAIL" in failed
    for problem in ("seat_operations = 1", "operator decisions", "hard limit evidence_mismatch",
                    "no result reached the operator"):
        assert problem in failed
    for text in (passed, failed):
        assert names[0] in text and text.count(names[1]) == 2


def test_landed_step_is_never_excused_even_with_stale_holds():
    scenarios = measured_scenarios()
    fresh = scenarios[alpha.FRESH]
    fresh.steps[0]["state"] = "built"
    fresh.observe("fallback", step="open", oracle_key="open")
    fresh.observe("no_driver", step="open")
    text = render(scenarios)
    assert "Unexcused fallback: open" in text
    assert "landed step has no driver" in text
    assert "Excused G3 fallback" not in text


def test_alpha_requires_steering_off_result_contents_and_strict_preflight():
    scenarios = measured_scenarios()
    fresh = scenarios[alpha.FRESH]
    fresh.observations[-1]["problems"] = ["the result carries no diff"]
    assert "the result carries no diff" in render(scenarios)
    fresh.steering = True
    del scenarios[alpha.PREFLIGHT[0]]
    text = render(scenarios)
    assert "V1: no measured ledger" in text
    assert "strict preflight pass not observed" in text


def test_receipt_lines_keep_dry_runs_distinct_from_real_receipts():
    assert alpha.receipt_lines(None) == [
        "Alpha receipt: NOT RECORDED (a real-model run the operator starts, per event)"]
    assert alpha.receipt_lines({"kind": "dry_run"}) == ["Alpha receipt: DRY RUN, not the receipt"]


def test_real_receipt_lists_all_fields_and_the_existing_containment_bar():
    receipt = {field: "not recorded" for field in alpha.FIELDS}
    receipt.update(kind="real", header={"platform": "win32", "workers_model": "openai/worker-free"},
                   containment={"workers": {"R-INV-0001-1": None}, "lead": ["workdir_separation_only"]})
    lines = alpha.receipt_lines(receipt)
    assert "Alpha receipt: RECORDED" in lines
    assert ledger.WINDOWS_UNQUALIFIED in lines
    assert all(any(line.startswith(f"{field}:") for line in lines) for field in alpha.FIELDS)
    assert [line for line in lines if "below containment minimum" in line] == [
        "workers: no label below containment minimum workdir_separation_only"]
    assert any("a -free id" in line for line in lines)
    assert "free: not ruled out (id rule only; catalog not read)" in lines
