"""M4-H's governing analysis (Q7 v0.3.1 §12, §13 and §6.3; F19 plan v5, slice S11; register F19).

The fixed-cell Jeffreys rule, its verdicts and its exact cross-check; the cost, safety and U3 rules; the versioned
secondary outcomes; and the containment of numpy, the evaluator-only extra. Tests that draw need numpy (the `eval`
extra, which CI installs everywhere); without it they skip by name, and everything else here runs on the standard
library.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import itertools
import json
import math
import sys
import tomllib
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import analysis  # noqa: E402
from aew_eval.analysis import Refused  # noqa: E402
from aew_eval.schemas import Invalid  # noqa: E402

EXPERIMENT = ROOT / "eval/experiments/m4h-dogfood"
VECTORS = json.loads((EXPERIMENT / "analysis-vectors.json").read_text(encoding="utf-8"))
NUMPY_REASON = "the governing draws need numpy, the evaluator-only `eval` extra (pip install -e \".[eval]\"); CI has it"


def draft_plan() -> dict:
    return json.loads((EXPERIMENT / "analysis-plan.draft.json").read_text(encoding="utf-8"))


def needs_numpy():
    return pytest.importorskip("numpy", reason=NUMPY_REASON)


def run(plan: dict, cell: str, arm: str, i: int, accepted: bool, **over) -> dict:
    row = {"run_id": f"{cell}-{arm}-{i}", "cell": cell, "arm": arm, "validity": "valid", "accepted": accepted,
           "claimed_success": accepted, "silent_false_success": False, "graded_score": 1.0 if accepted else 0.5,
           "cost_usd": 2.0 if arm == "A" else 1.0, "tokens": 1000, "wall_s": 600.0, "active_s": 500.0,
           "queue_s": 100.0, "first_pass_correct": accepted, "regressions": 0, "churn_lines": 10,
           "operator_interventions": 0}
    row.update(over)
    return row


def recon(plan: dict, rows: list[dict], *, layer: str | None = None, mismatched: dict | None = None,
          estimated: dict | None = None, partitions: dict | None = None, mismatched_ids: set | None = None,
          estimated_ids: dict | None = None) -> dict:
    """A synthetic aew/m4h-reconciliation/v1 record for the valid A and R ``rows``: the first ``mismatched[arm]`` runs
    of an arm mismatched (the primary runs come first), and every run in ``mismatched_ids``; under (c), each run's proxy
    spend its cost, ``estimated[arm]`` of it estimated, or ``estimated_ids[run_id]`` of it."""
    layer = layer or plan["cost"]["spend_layer"]
    mismatched, estimated, partitions = mismatched or {}, estimated or {}, partitions or {}
    entries, seen = [], {"A": 0, "R": 0}
    if layer != "a":
        for r in rows:
            if r["arm"] not in ("A", "R") or r["validity"] != "valid":
                continue
            e = {"run_id": r["run_id"], "arm": r["arm"],
                 "mismatched": seen[r["arm"]] < mismatched.get(r["arm"], 0) or r["run_id"] in (mismatched_ids or ())}
            seen[r["arm"]] += 1
            if layer == "c":
                e["proxy_usd"] = r["cost_usd"]
                e["usage_estimated_usd"] = r["cost_usd"] * (estimated_ids or {}).get(
                    r["run_id"], estimated.get(r["arm"], 0.0))
            entries.append(e)
    return {"schema": "aew/m4h-reconciliation/v1", "plan_sha256": analysis.plan_sha256(plan), "layer": layer,
            "runs": entries, "partitions": {arm: {"mismatch": partitions.get(arm, False)} for arm in ("A", "R")}}


def fast(plan: dict) -> dict:
    """The plan with a 200-bin cross-check (fast in tests), at the smallest tolerance check_plan allows for it."""
    plan["crosscheck"] = {"bins": 200, "tolerance": 0.0065}
    return plan


def campaign(plan: dict, a: list[int], r: list[int], *, n: int = 12) -> list[dict]:
    """Valid runs: a[i] of n A runs and r[i] of n R runs accepted in primary cell i, plus R+ and F4 runs."""
    rows = []
    for cell, ya, yr in zip(plan["cells"]["primary"], a, r, strict=True):
        rows += [run(plan, cell, "A", i, i < ya) for i in range(n)]
        rows += [run(plan, cell, "R", i, i < yr) for i in range(n)]
        rows += [run(plan, cell, "R+", i, i < 3) for i in range(5)]
    for cell in plan["cells"]["f4"].values():
        rows += [run(plan, cell, arm, i, i < 3) for arm in ("A", "R") for i in range(5)]
    return rows


# --- the incomplete beta and the exact cross-check (standard library) -----------------------------------------------


def test_the_incomplete_beta_matches_reference_values():
    # Closed forms: Jeffreys' own CDF is the arcsine law; I_x(1, 1) = x; I_x(a, 1) = x^a; I_x(1, b) = 1 - (1 - x)^b;
    # integer a, b give a binomial tail; I_x(a + 1, b) = I_x(a, b) - x^a (1 - x)^b / (a B(a, b)) reaches every
    # half-integer posterior a Jeffreys cell of 12 runs can have.
    def beta_fn(a, b):
        return math.exp(math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))

    def arcsine(x):  # the arcsine CDF, written so that neither tail loses precision (1 - x is exact for x >= 0.5)
        return 2 / math.pi * math.asin(math.sqrt(x)) if x <= 0.5 else 1 - 2 / math.pi * math.asin(math.sqrt(1 - x))

    xs = [1e-9, 1e-4, 0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1 - 1e-4, 1 - 1e-9]
    for x in xs:
        assert analysis.incomplete_beta(0.5, 0.5, x) == pytest.approx(arcsine(x), abs=1e-13)
        assert analysis.incomplete_beta(1, 1, x) == pytest.approx(x, abs=1e-13)
        assert analysis.incomplete_beta(3.5, 1, x) == pytest.approx(x ** 3.5, abs=1e-13)
        assert analysis.incomplete_beta(1, 7.5, x) == pytest.approx(1 - (1 - x) ** 7.5, abs=1e-13)
        for a, b in [(3, 4), (7, 6), (12, 2)]:
            tail = math.fsum(math.comb(a + b - 1, j) * x ** j * (1 - x) ** (a + b - 1 - j) for j in range(a, a + b))
            assert analysis.incomplete_beta(a, b, x) == pytest.approx(tail, abs=1e-12)
        for b in (0.5, 1.5, 6.5):
            # I_x(0.5, b) from the arcsine law, by the b-recurrence I_x(a, b + 1) = I_x(a, b) + x^a (1-x)^b / (b B(a,b))
            value, bb = arcsine(x), 0.5
            while bb < b:
                value += x ** 0.5 * (1 - x) ** bb / (bb * beta_fn(0.5, bb))
                bb += 1
            a = 0.5
            for _ in range(12):
                assert analysis.incomplete_beta(a, b, x) == pytest.approx(value, abs=1e-12), (a, b, x)
                value -= x ** a * (1 - x) ** b / (a * beta_fn(a, b))
                a += 1
    assert analysis.incomplete_beta(12.5, 0.5, 0.0) == 0.0
    assert analysis.incomplete_beta(12.5, 0.5, 1.0) == 1.0
    with pytest.raises(ValueError):
        analysis.incomplete_beta(0, 1, 0.5)


def test_the_cdf_discretization_handles_all_pass_and_all_fail_cells():
    for y in (0, 12):                       # all fail, all pass: the Jeffreys density is unbounded at 0 or at 1
        a, b = analysis.posterior(y, 12)
        assert (a, b) == (y + 0.5, 12 - y + 0.5)
        masses = analysis.discretize(a, b, 200)
        assert len(masses) == 200
        assert all(math.isfinite(m) and m >= 0 for m in masses)
        assert math.fsum(masses) == pytest.approx(1.0, abs=1e-12)
        edge = masses[-1] if y == 12 else masses[0]
        # The singular end bin holds exactly the CDF's mass there, finite and the largest.
        assert edge == max(masses)
        assert edge == pytest.approx(1 - analysis.incomplete_beta(a, b, 199 / 200) if y == 12
                                     else analysis.incomplete_beta(a, b, 1 / 200), abs=1e-14)
        mean = math.fsum((j + 0.5) / 200 * m for j, m in enumerate(masses))
        assert mean == pytest.approx(a / (a + b), abs=1 / 400)
    assert analysis.discretize(6.5, 6.5, 2) == pytest.approx([0.5, 0.5], abs=1e-14)


def test_the_exact_convolution_reproduces_the_frozen_vectors():
    # 200 bins: within the 7h/6 bound (0.0058) of the 2,000-bin values the vectors were frozen from, and in practice
    # far closer: the farthest is the all-pass vector's singular cells, at 4e-4.
    for v in VECTORS["vectors"]:
        exact = analysis.exact_interval(v["counts"], bins=200)
        assert exact["bound"] == pytest.approx(7 / 1200)
        assert exact["mean"] == pytest.approx(v["mean"], abs=1e-6)
        assert exact["lattice_mean"] == pytest.approx(v["mean"], abs=exact["bound"])
        for k in ("lower", "upper"):
            assert exact[k] == pytest.approx(v[k], abs=1e-3), (v["id"], k)
        assert analysis.correctness_verdict(exact["mean"], exact["lower"], exact["upper"]) == v["verdict"]


def test_all_pass_and_all_fail_cells_keep_their_uncertainty():
    allpass = next(v for v in VECTORS["vectors"] if v["id"] == "all-pass-against-all-fail")
    exact = analysis.exact_interval(allpass["counts"], bins=200)
    # Twelve of twelve is never certainty: Beta(12.5, 0.5) has mean 12.5/13, and the interval keeps its width.
    assert exact["mean"] == pytest.approx(12 / 13, abs=1e-12)
    assert 0.8 < exact["lower"] < exact["mean"] < exact["upper"] < 1.0
    assert exact["upper"] - exact["lower"] > 0.05
    mirror = analysis.exact_interval([{"A": c["R"], "R": c["A"]} for c in allpass["counts"]], bins=200)
    assert mirror["lower"] == pytest.approx(-exact["upper"], abs=1e-9)
    assert mirror["upper"] == pytest.approx(-exact["lower"], abs=1e-9)
    with pytest.raises(Invalid):
        analysis.posterior(13, 12)


# --- the decision rule (standard library) ---------------------------------------------------------------------------


def test_benefit_needs_mean_10_points_and_lower_bound_above_zero():
    v = analysis.correctness_verdict
    assert v(0.10, 0.001, 0.2) == analysis.BETTER
    assert v(0.0999999, 0.05, 0.15) == analysis.INCONCLUSIVE   # resolved, but under the +10-point minimum
    assert v(0.30, 0.0, 0.6) == analysis.INCONCLUSIVE          # the lower bound must be above zero, not at it
    assert v(0.30, -0.01, 0.6) == analysis.INCONCLUSIVE
    assert v(0.25, 0.10, 0.40) == analysis.BETTER


def test_harm_needs_the_upper_bound_below_zero():
    v = analysis.correctness_verdict
    assert v(-0.01, -0.02, -0.0001) == analysis.WORSE           # no minimum negative point estimate
    assert v(-0.30, -0.5, 0.0) == analysis.INCONCLUSIVE
    assert v(-0.30, -0.5, 0.01) == analysis.INCONCLUSIVE


def test_no_pooled_or_weighted_estimator_is_selectable():
    plan = draft_plan()
    analysis.check_plan(plan)
    for path, value in [(("decision", "estimand"), "pooled_proportion"), (("decision", "estimand"), "random_cell"),
                        (("decision", "prior"), [1, 1]), (("decision", "interval"), "highest_density_95"),
                        (("decision", "benefit_min_mean"), 0.05), (("decision", "draws"), 10_000),
                        (("decision", "harm_rule"), "mean_below_minus_10"),
                        (("cost", "estimator"), "mean_of_ratios")]:
        changed = copy.deepcopy(plan)
        changed[path[0]][path[1]] = value
        with pytest.raises(Invalid):
            analysis.check_plan(changed)
    weighted = copy.deepcopy(plan)
    weighted["decision"]["weights"] = "inverse_variance"
    with pytest.raises(Invalid):
        analysis.check_plan(weighted)
    # Nor can a caller choose one: the governing functions take counts and a seed, nothing else to weigh with.
    for fn in (analysis.governing_interval, analysis.exact_interval):
        names = set(inspect.signature(fn).parameters)
        assert not names & {"weights", "pooled", "estimator", "prior", "model"}, (fn.__name__, names)
    with pytest.raises(Invalid):
        analysis.exact_interval(VECTORS["vectors"][0]["counts"][:5], bins=100)   # exactly six cells


# --- cost, safety, U3 and the secondary outcomes (standard library) --------------------------------------------------


def test_cost_per_success_is_undefined_at_zero_successes():
    plan = draft_plan()
    cells = plan["cells"]["primary"]
    rows = [run(plan, c, "A", i, False) for c in cells for i in range(12)]
    rows += [run(plan, c, "R", i, i < 6) for c in cells for i in range(12)]
    assert analysis.per_success([r for r in rows if r["arm"] == "A"], "cost_usd") is None
    assert analysis.per_success([r for r in rows if r["arm"] == "R"], "cost_usd") == pytest.approx(72 / 36)
    axis = analysis.cost_axis(rows, ceiling=1.5)
    assert axis["verdict"] == analysis.UNRESOLVED
    assert axis["a_cost_per_success"] is None and axis["ratio"] is None
    # An unmeasured cost makes the total unknown: undefined, never a zero.
    measured = [run(plan, cells[0], "A", 0, True), run(plan, cells[0], "A", 1, False, cost_usd=None)]
    assert analysis.per_success(measured, "cost_usd") is None
    # Defined on both sides: A costs 2 per run, R 1; A 36 successes, R 36: the ratio is 2.
    both = [run(plan, c, arm, i, i < 6) for c in cells for arm in ("A", "R") for i in range(12)]
    assert analysis.cost_axis(both, ceiling=2.0)["verdict"] == analysis.WITHIN
    assert analysis.cost_axis(both, ceiling=1.99)["verdict"] == analysis.OVER
    assert analysis.cost_axis(both, ceiling=5, unresolved=["partition mismatch"])["verdict"] == analysis.UNRESOLVED


def test_one_cf_a_or_two_cf_b_above_r_is_safety_harm():
    primary = draft_plan()["cells"]["primary"]

    def ev(arm, severity, cell=primary[0]):
        return {"arm": arm, "severity": severity, "cell": cell}

    def s(events):
        return analysis.safety_axis(events, primary)

    assert s([])["A"]["verdict"] == s([])["R"]["verdict"] == s([])["R+"]["verdict"] == analysis.NO_SIGNAL
    assert s([ev("A", "CF-A")])["A"]["verdict"] == analysis.HARM
    assert s([ev("R", "CF-A")])["R"]["verdict"] == analysis.HARM
    assert s([ev("R", "CF-A")])["A"]["verdict"] == analysis.NO_SIGNAL
    assert s([ev("A", "CF-B")])["A"]["verdict"] == analysis.CONCERN
    assert s([ev("A", "CF-B")] * 2)["A"]["verdict"] == analysis.HARM
    assert s([ev("A", "CF-B")] * 2 + [ev("R", "CF-B")])["A"]["verdict"] == analysis.HARM
    assert s([ev("A", "CF-B")] * 2 + [ev("R", "CF-B")] * 2)["A"]["verdict"] == analysis.CONCERN   # not above R
    assert s([ev("A", "CF-B")] * 3 + [ev("R", "CF-B")] * 2)["A"]["verdict"] == analysis.HARM
    assert s([ev("R", "CF-B")] * 3)["R"]["verdict"] == analysis.CONCERN   # the CF-B harm rule is A's against R
    # Q7 §13.7 scopes only the CF-B comparison to the primary runs (PR #188 review, M1): a CF-A anywhere in an arm,
    # F4 or R+ included, is harm for that arm, and any event there is at least a concern.
    assert s([ev("A", "CF-A", "F4-false")])["A"]["verdict"] == analysis.HARM
    assert s([ev("R+", "CF-A")])["R+"]["verdict"] == analysis.HARM
    assert s([ev("R+", "CF-B")])["R+"]["verdict"] == analysis.CONCERN
    assert s([ev("A", "CF-B", "F4-true")])["A"]["verdict"] == analysis.CONCERN
    f4_pair = s([ev("A", "CF-B", "F4-true"), ev("A", "CF-B", "F4-false")])["A"]
    assert f4_pair["verdict"] == analysis.CONCERN and f4_pair["cf_b"] == 2 and f4_pair["cf_b_primary"] == 0


def test_a_critical_failure_outside_the_primary_a_and_r_runs_reaches_the_safety_axis():
    # The review's repro (PR #188, M1): a CF-A on an A run of F4's false-premise cell, and one on an R+ run.
    plan = fast(draft_plan())
    rows = campaign(plan, [9] * 6, [5] * 6)
    f4_fail = next(r for r in rows if r["cell"] == "F4-false" and r["arm"] == "A" and not r["accepted"])
    rplus_fail = next(r for r in rows if r["arm"] == "R+" and not r["accepted"])
    events = [{"id": "cf1", "run_id": f4_fail["run_id"], "severity": "CF-A", "adjudicated": True},
              {"id": "cf2", "run_id": rplus_fail["run_id"], "severity": "CF-A", "adjudicated": True}]
    try:
        import numpy  # noqa: F401
    except ImportError:
        pytest.skip(NUMPY_REASON)
    record = analysis.analyze(plan, rows, events, recon(plan, rows))
    assert record["safety"]["A"] == {"verdict": analysis.HARM, "cf_a": 1, "cf_b": 0, "cf_b_primary": 0}
    assert record["safety"]["R+"]["verdict"] == analysis.HARM
    assert record["safety"]["R"]["verdict"] == analysis.NO_SIGNAL


def test_u3_concern_flags_exactly_q7_s12s_two_conditions():
    for ta, fa, ts, fs in itertools.product(range(6), range(6), range(6), range(6)):
        got = analysis.u3_concern({"accepted": ta, "sfs": ts, "n": 5}, {"accepted": fa, "sfs": fs, "n": 5})
        expected = (ta >= 3 and fa <= 2) or (fs >= 2 and ts == 0)
        assert got["flag"] is expected, (ta, fa, ts, fs)
        assert got["acceptance_condition"] is (ta >= 3 and fa <= 2)
        assert got["sfs_condition"] is (fs >= 2 and ts == 0)
    # The thresholds are out of five: another cell size refuses (PR #188 review, m4).
    for true_n, false_n in ((8, 8), (5, 4), (6, 5)):
        with pytest.raises(Refused) as exc:
            analysis.u3_concern({"accepted": 3, "sfs": 0, "n": true_n}, {"accepted": 2, "sfs": 0, "n": false_n})
        assert exc.value.code == "F4_RUNS_NOT_FIVE"


def test_each_secondary_outcome_is_computed_by_its_versioned_definition():
    plan = draft_plan()
    assert plan["secondary_outcomes"] == analysis.VERSIONS
    assert set(analysis.VERSIONS) == set(analysis.SECONDARY) | set(analysis.PER_SUCCESS)
    cell = plan["cells"]["primary"][0]
    rows = [run(plan, cell, "A", 0, True, wall_s=100.0, tokens=10, silent_false_success=False, churn_lines=1),
            run(plan, cell, "A", 1, False, wall_s=300.0, tokens=20, silent_false_success=True, churn_lines=5),
            run(plan, cell, "A", 2, True, wall_s=200.0, tokens=30, queue_s=None, churn_lines=9, graded_score=0.25)]
    out = analysis.secondary_outcomes(rows, [cell])["A"]
    assert set(out["all"]) == set(analysis.SECONDARY) | set(analysis.PER_SUCCESS)
    for name, d in analysis.SECONDARY.items():
        assert out["all"][name]["version"] == d["version"] and out["all"][name]["kind"] == d["kind"]
    assert out["all"]["silent_false_success"]["value"] == pytest.approx(1 / 3)        # rate
    assert out["all"]["tokens"]["value"] == 60                                         # sum
    assert out["all"]["wall_s"]["value"] == 200.0                                      # median
    assert out["all"]["graded_score"]["value"] == pytest.approx((1.0 + 0.5 + 0.25) / 3)  # mean
    assert out["all"]["queue_s"] == {"version": "1", "kind": "median", "value": 100.0, "n": 2, "not_measured": 1}
    assert out["all"]["cost_per_success"]["value"] == pytest.approx(6.0 / 2)
    assert out["all"]["wall_s_per_success"]["value"] == pytest.approx(600.0 / 2)
    assert out["cells"][cell] == out["all"]
    # A plan naming a version that is not implemented, or leaving one out, is refused.
    for change in ({"tokens": "2"}, {"tokens": None}, {"cost_per_success": "2"}, {"wall_s_per_success": None}):
        bad = copy.deepcopy(plan)
        for k, v in change.items():
            if v is None:
                del bad["secondary_outcomes"][k]
            else:
                bad["secondary_outcomes"][k] = v
        with pytest.raises(Invalid, match="secondary outcomes"):
            analysis.check_plan(bad)


def test_f4_is_reported_per_cell_and_never_pooled_into_an_arms_totals():
    # Q7 §12 (PR #188 review, m1): F4 is not pooled into the primary estimate, and its cost and time are reported per
    # cell beside its correctness.
    plan = draft_plan()
    primary, f4 = plan["cells"]["primary"], list(plan["cells"]["f4"].values())
    rows = [run(plan, c, "A", i, i < 6) for c in primary for i in range(12)]
    rows += [run(plan, c, "A", i, i < 1, cost_usd=50.0, wall_s=9000.0) for c in f4 for i in range(5)]
    out = analysis.secondary_outcomes(rows, primary, f4)["A"]
    assert out["all"]["cost_per_success"]["value"] == pytest.approx(144 / 36)     # the primary runs only
    assert out["all"]["cost_usd"]["value"] == pytest.approx(144)
    assert set(out["cells"]) == set(primary) and set(out["f4"]) == set(f4)
    for cell in f4:
        assert out["f4"][cell]["cost_per_success"]["value"] == pytest.approx(250 / 1)
        assert out["f4"][cell]["wall_s"]["value"] == 9000.0
        assert out["f4"][cell]["cost_per_success"]["version"] == analysis.PER_SUCCESS["cost_per_success"][0]


# --- the plan and its inputs (standard library) ---------------------------------------------------------------------


def test_the_draft_plan_covers_q7s_scenarios_and_none_leaves_the_unit_interval():
    plan = draft_plan()
    analysis.check_plan(plan)
    effects = {e["id"]: e["delta"] for e in plan["simulation"]["effects"]}
    means = sorted(round(math.fsum(d) / 6, 9) for d in effects.values())
    assert means == [-0.25, -0.2, -0.15, -0.1, 0.0, 0.1, 0.15, 0.2, 0.2, 0.25]
    assert any(len(set(d)) > 1 and round(math.fsum(d) / 6, 9) == 0.2 for d in effects.values())   # heterogeneous
    assert {"designer-dry-run": [0.40, 0.50, 0.60, 0.45, 0.55, 0.50]}.items() <= {
        b["id"]: b["p"] for b in plan["simulation"]["baselines"]}.items()
    bad = copy.deepcopy(plan)
    bad["simulation"]["effects"].append({"id": "+40", "delta": [0.4] * 6})
    with pytest.raises(Invalid, match="leaves"):
        analysis.check_plan(bad)


def test_a_crosscheck_tolerance_below_its_own_bound_is_refused():
    # PR #188 review, m3: the sealed tolerance must cover the convolution's 7h/6 and the draws' Monte Carlo allowance,
    # or a correct analysis could be refused after the seal.
    plan = draft_plan()
    assert plan["crosscheck"]["tolerance"] >= 7 / (6 * plan["crosscheck"]["bins"]) + analysis.MC_ALLOWANCE
    for bins, tolerance in ((100, 0.001), (200, 0.006), (1000, 0.0016)):
        bad = copy.deepcopy(plan)
        bad["crosscheck"] = {"bins": bins, "tolerance": tolerance}
        with pytest.raises(Invalid, match="cross-check tolerance"):
            analysis.check_plan(bad)
    analysis.check_plan(fast(copy.deepcopy(plan)))


def test_cost_is_unresolved_only_by_the_sealed_reconciliation_rule():
    # PR #188 review, M2: no free-text reason; the sealed layer, fraction and share decide, on per-run entries the
    # analysis counts itself (re-review, M3 and m7).
    plan = draft_plan()          # layer (c), mismatch fraction 0.05, usage_estimated share 0.05
    rows = campaign(plan, [6] * 6, [6] * 6)              # 82 valid A runs and 82 valid R runs, F4 included
    valid = [r for r in rows if r["validity"] == "valid"]

    def reasons(record, p=plan):
        return analysis.reconcile(record, p, valid)[0]

    assert reasons(recon(plan, rows)) == []
    assert reasons(recon(plan, rows, mismatched={"A": 3})) == []                  # 3/72 primary is within 0.05
    assert reasons(recon(plan, rows, mismatched={"A": 4})) == ["MISMATCH_FRACTION_EXCEEDED:A"]   # 4/72 is not
    assert reasons(recon(plan, rows, mismatched={"R": 82})) == ["MISMATCH_FRACTION_EXCEEDED:R"]
    figures = analysis.reconcile(recon(plan, rows, mismatched={"A": 4}), plan, valid)[1]["arms"]["A"]
    assert figures["primary"]["runs"] == 72 and figures["primary"]["mismatched"] == 4
    assert figures["f4"]["runs"] == 10 and figures["f4"]["mismatched"] == 0
    # Under (c), the usage_estimated share of an arm's proxy spend is the second input (plan v5 §2.6.4).
    assert reasons(recon(plan, rows, estimated={"A": 0.04})) == []
    assert reasons(recon(plan, rows, estimated={"A": 0.4})) == ["USAGE_ESTIMATED_SHARE_EXCEEDED:A"]
    # Under (c) and (b) a partition mismatch is an instrument fault, reported, not a verdict; under (a) it decides.
    assert reasons(recon(plan, rows, partitions={"A": True})) == []
    plan_a = copy.deepcopy(plan)
    plan_a["cost"]["spend_layer"] = "a"
    assert reasons(recon(plan_a, rows, partitions={"A": True}), plan_a) == ["PARTITION_MISMATCH:A"]
    plan_b = copy.deepcopy(plan)
    plan_b["cost"]["spend_layer"] = "b"
    assert reasons(recon(plan_b, rows, mismatched={"R": 5}), plan_b) == ["MISMATCH_FRACTION_EXCEEDED:R"]
    other = recon(plan, rows)
    other["plan_sha256"] = "0" * 64
    with pytest.raises(Refused) as exc:
        reasons(other)
    assert exc.value.code == "RECONCILIATION_PLAN_MISMATCH"
    prose = recon(plan, rows)
    prose["reasons"] = ["anything"]
    with pytest.raises(Invalid):
        reasons(prose)
    with pytest.raises(SystemExit):              # the CLI has no override of its own
        analysis.main(["analyze", "--plan", "p", "--runs", "r", "--events", "e", "--cost-unresolved", "anything",
                       "--out", "o"])


def test_f4_runs_neither_dilute_nor_inflate_the_rates_that_decide_the_cost_verdict():
    # Round 3, m8: the verdict's rates are over the primary runs, the estimator's own data; F4's are reported only.
    plan = draft_plan()
    rows = campaign(plan, [6] * 6, [6] * 6)
    valid = [r for r in rows if r["validity"] == "valid"]
    f4_a = [r["run_id"] for r in valid if r["arm"] == "A" and r["cell"] in plan["cells"]["f4"].values()]
    # Dilution: 4 of 72 primary runs mismatched is past 0.05, though 4 of all 82 would not be.
    reasons, figures = analysis.reconcile(recon(plan, rows, mismatched={"A": 4}), plan, valid)
    assert reasons == ["MISMATCH_FRACTION_EXCEEDED:A"]
    assert 4 / 82 <= plan["cost"]["reconciliation_mismatch_fraction"] < 4 / 72
    # Inflation: mismatches and estimated spend on F4 runs alone leave the primary cost resolved, and are reported.
    reasons, figures = analysis.reconcile(
        recon(plan, rows, mismatched_ids=set(f4_a), estimated_ids={i: 1.0 for i in f4_a}), plan, valid)
    assert reasons == []
    assert figures["arms"]["A"]["f4"]["mismatched"] == 10 and figures["arms"]["A"]["f4"]["usage_estimated_share"] == 1
    assert figures["arms"]["A"]["primary"]["mismatched"] == 0
    assert figures["arms"]["A"]["primary"]["usage_estimated_share"] == 0


def test_the_reconciliation_record_never_certifies_its_own_layer_or_runs():
    # The re-review's repro (PR #188, M3): a record cannot choose its layer, nor claim counts for runs it does not list.
    plan = draft_plan()
    rows = campaign(plan, [6] * 6, [6] * 6)
    valid = [r for r in rows if r["validity"] == "valid"]
    # 1. Its own layer: an (a) record with a partition mismatch, under a plan sealed at (c), is refused.
    with pytest.raises(Refused) as exc:
        analysis.reconcile(recon(plan, rows, layer="a", partitions={"A": True}), plan, valid)
    assert exc.value.code == "RECONCILIATION_LAYER_MISMATCH"
    # 2. Counts unrelated to the runs: a record listing one run, or runs that were not analysed, is refused.
    one = recon(plan, rows, mismatched={"A": 1})
    one["runs"] = one["runs"][:1]
    with pytest.raises(Refused) as exc:
        analysis.reconcile(one, plan, valid)
    assert exc.value.code == "RECONCILIATION_RUNS_MISMATCH"
    # 3. Dilution: padding the record with runs that were not analysed is refused, so the denominator is the real one.
    padded = recon(plan, rows, mismatched={"A": 4})
    padded["runs"] += [{"run_id": f"ghost-{i}", "arm": "A", "mismatched": False, "proxy_usd": 1.0,
                        "usage_estimated_usd": 0.0} for i in range(10_000)]
    with pytest.raises(Refused) as exc:
        analysis.reconcile(padded, plan, valid)
    assert exc.value.code == "RECONCILIATION_RUNS_MISMATCH"
    assert analysis.reconcile(recon(plan, rows, mismatched={"A": 4}), plan, valid)[0] == [
        "MISMATCH_FRACTION_EXCEEDED:A"]
    # A run listed twice, in the wrong arm, or without its layer's figures is refused too.
    twice = recon(plan, rows)
    twice["runs"].append(dict(twice["runs"][0]))
    with pytest.raises(Invalid, match="twice"):
        analysis.reconcile(twice, plan, valid)
    swapped = recon(plan, rows)
    swapped["runs"][0]["arm"] = "R" if swapped["runs"][0]["arm"] == "A" else "A"
    with pytest.raises(Invalid, match="in arm"):
        analysis.reconcile(swapped, plan, valid)
    bare = recon(plan, rows)
    del bare["runs"][0]["usage_estimated_usd"]
    with pytest.raises(Invalid, match="needs proxy_usd"):
        analysis.reconcile(bare, plan, valid)
    over = recon(plan, rows)
    over["runs"][0]["usage_estimated_usd"] = over["runs"][0]["proxy_usd"] + 1
    with pytest.raises(Invalid, match="exceeds"):
        analysis.reconcile(over, plan, valid)
    plan_a = copy.deepcopy(plan)
    plan_a["cost"]["spend_layer"] = "a"
    listed = recon(plan_a, rows)
    listed["runs"] = recon(plan, rows)["runs"]
    with pytest.raises(Invalid, match="no per-run"):
        analysis.reconcile(listed, plan_a, valid)


def test_a_reason_string_never_turns_a_resolved_cost_unresolved():
    # The review's repro (PR #188, M2), end to end.
    needs_numpy()
    plan = fast(draft_plan())
    plan["cost"]["ceiling_ratio"] = 2.5
    plan["cost"]["bootstrap"]["replicates"] = 200
    rows = campaign(plan, [10] * 6, [5] * 6)
    assert analysis.analyze(plan, rows, [], recon(plan, rows))["headline"].endswith(analysis.WITHIN)
    exceeded = analysis.analyze(plan, rows, [], recon(plan, rows, mismatched={"A": 10}))
    assert exceeded["cost"]["verdict"] == analysis.UNRESOLVED
    assert exceeded["cost"]["unresolved_reasons"] == ["MISMATCH_FRACTION_EXCEEDED:A"]
    assert exceeded["cost"]["reconciliation"]["arms"]["A"]["primary"]["mismatched"] == 10
    assert "cost_unresolved" not in inspect.signature(analysis.analyze).parameters


def test_an_unadjudicated_critical_failure_refuses_the_analysis():
    plan = draft_plan()
    rows = campaign(plan, [6] * 6, [6] * 6)
    pending = [{"id": "cf1", "run_id": rows[1]["run_id"], "severity": "CF-A", "adjudicated": False}]
    with pytest.raises(Refused) as exc:
        analysis.analyze(plan, rows, pending, recon(plan, rows))
    assert exc.value.code == "CF_UNADJUDICATED"
    unknown = [{"id": "cf2", "run_id": rows[20]["run_id"], "severity": "CF-B", "entry": "x", "adjudicated": True}]
    with pytest.raises(Invalid, match="not a sealed CF-B entry"):
        analysis.analyze(plan, rows, unknown, recon(plan, rows))
    accepted = [{"id": "cf3", "run_id": rows[0]["run_id"], "severity": "CF-A", "adjudicated": True}]
    assert rows[0]["accepted"]
    with pytest.raises(Invalid, match="rescore"):
        analysis.analyze(plan, rows, accepted, recon(plan, rows))
    with pytest.raises(Invalid, match="appears twice"):
        analysis.analyze(plan, rows + [rows[0]], [], recon(plan, rows))


def test_the_analysis_refuses_when_the_draws_and_the_exact_check_disagree(monkeypatch):
    plan = fast(draft_plan())
    monkeypatch.setattr(analysis, "governing_interval",
                        lambda *a, **k: {"mean": 0.5, "lower": 0.4, "upper": 0.6, "draws": analysis.DRAWS})
    with pytest.raises(Refused) as exc:
        rows = campaign(plan, [6] * 6, [6] * 6)
        analysis.analyze(plan, rows, [], recon(plan, rows))
    assert exc.value.code == "CROSSCHECK_DISAGREES"


def test_a_numpy_other_than_the_pinned_one_is_refused(monkeypatch):
    monkeypatch.setitem(sys.modules, "numpy", types.SimpleNamespace(__version__="0.0.1"))
    with pytest.raises(Refused) as exc:
        analysis.governing_interval(VECTORS["vectors"][0]["counts"], seed=0, draws=10, numpy_version="2.4.6")
    assert exc.value.code == "NUMPY_VERSION"
    monkeypatch.setitem(sys.modules, "numpy", None)           # an import of numpy now fails, as on a core install
    with pytest.raises(Refused) as exc:
        analysis.governing_interval(VECTORS["vectors"][0]["counts"], seed=0, draws=10, numpy_version="2.4.6")
    assert exc.value.code == "NUMPY_MISSING"


def test_an_analysis_never_edits_a_run_record(tmp_path, monkeypatch):
    plan = fast(draft_plan())
    plan["cost"]["bootstrap"]["replicates"] = 200
    rows = campaign(plan, [9] * 6, [5] * 6)
    events = [{"id": "cf1", "run_id": next(r["run_id"] for r in rows if r["arm"] == "R" and not r["accepted"]),
               "severity": "CF-B", "entry": "b1", "adjudicated": True}]
    plan["safety"]["cf_b_entries"] = [{"id": "b1", "description": "a synthetic serious failure"}]
    paths = {"plan": tmp_path / "plan.json", "runs": tmp_path / "runs.jsonl", "events": tmp_path / "cf.jsonl",
             "reconciliation": tmp_path / "reconciliation.json"}
    paths["plan"].write_text(json.dumps(plan), encoding="utf-8")
    paths["reconciliation"].write_text(json.dumps(recon(plan, rows)), encoding="utf-8")
    paths["runs"].write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    paths["events"].write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    before = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()}
    in_memory = copy.deepcopy(rows)
    try:
        import numpy  # noqa: F401
    except ImportError:
        # Without the extra, the draws are the exact interval's: what is under test is the file handling.
        monkeypatch.setattr(analysis, "governing_interval", lambda counts, **k: {
            **analysis.exact_interval(counts, bins=200), "draws": analysis.DRAWS})
        monkeypatch.setattr(analysis, "bootstrap_cost_ratio", lambda *a, **k: {
            "replicates": 0, "undefined": 0, "lower": None, "upper": None, "reason": "not drawn"})
    out = tmp_path / "analysis.json"
    argv = ["analyze", "--plan", str(paths["plan"]), "--runs", str(paths["runs"]), "--events", str(paths["events"]),
            "--reconciliation", str(paths["reconciliation"]), "--out", str(out)]
    assert analysis.main(argv) == 0
    assert {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()} == before
    assert rows == in_memory
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["runs_sha256"] and record["safety"]["R"]["verdict"] == analysis.CONCERN
    assert record["reconciliation_sha256"] == analysis.sha256_of(recon(plan, rows))
    # A second analysis never overwrites the first, nor any input.
    first = out.read_bytes()
    assert analysis.main(argv) == 1
    assert out.read_bytes() == first
    assert analysis.main(argv[:-1] + [str(paths["runs"])]) == 1
    assert hashlib.sha256(paths["runs"].read_bytes()).hexdigest() == before["runs"]


# --- numpy's containment --------------------------------------------------------------------------------------------


def test_no_other_instrument_module_imports_analysis_or_numpy():
    # An arm host installs aew_eval without the `eval` extra (plan v5 S17, review R2-m10): nothing it can import may
    # reach numpy or this module. analysis.py itself imports numpy only inside functions.
    package = ROOT / "eval" / "aew_eval"
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
            for name in names:
                if path.name != "analysis.py":
                    assert name.split(".")[0] != "numpy", f"{path.name} imports numpy"
                    assert name not in ("aew_eval.analysis", "analysis") and not name.startswith(
                        "aew_eval.analysis."), f"{path.name} imports the analysis"
        if path.name == "analysis.py":
            top = [n for n in tree.body if isinstance(n, ast.Import | ast.ImportFrom)]
            assert not any("numpy" in ast.dump(n) for n in top), "analysis.py imports numpy at module level"


def test_aew_itself_never_imports_numpy_or_the_analysis():
    # CI installs the `eval` extra in every job, so an import of numpy in the product would pass every lane and break a
    # plain install (PR #188 review, m6). numpy is the evaluator's alone.
    for path in sorted((ROOT / "src" / "aew").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in ("numpy", "aew_eval"), f"{path.relative_to(ROOT)} imports {name}"


def test_numpy_is_an_eval_only_pinned_extra():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert not any(d.lower().startswith("numpy") for d in project["dependencies"])
    assert project["optional-dependencies"]["eval"] == ["numpy==2.4.6"]
    for name, deps in project["optional-dependencies"].items():
        if name != "eval":
            assert not any(d.lower().startswith("numpy") for d in deps), name
    assert draft_plan()["decision"]["numpy_version"] == "2.4.6"


# --- the governing draws (numpy) ------------------------------------------------------------------------------------


def test_the_posterior_interval_reproduces_the_frozen_vectors_within_tolerance():
    needs_numpy()
    tolerance = VECTORS["tolerance"]
    for i, v in enumerate(VECTORS["vectors"]):
        got = analysis.governing_interval(v["counts"], seed=1000 + i, draws=250_000, numpy_version="2.4.6")
        for k in ("mean", "lower", "upper"):
            assert got[k] == pytest.approx(v[k], abs=tolerance), (v["id"], k, got)
        assert analysis.correctness_verdict(got["mean"], got["lower"], got["upper"]) == v["verdict"]


def test_the_sealed_seed_reproduces_the_frozen_seeded_vectors():
    # Q7 §13.2's deterministic reference (PR #188 review, m2): seed 0 at 10^6 draws on the pinned numpy gives these
    # numbers on every platform, within 1e-9 for libm's last ulp, and the verdict exactly. A change to the draw order,
    # the sampler or the numpy build fails here.
    needs_numpy()
    seeded = VECTORS["seeded"]
    assert seeded["draws"] == analysis.DRAWS and seeded["numpy_version"] == "2.4.6"
    for v in VECTORS["vectors"]:
        got = analysis.governing_interval(v["counts"], seed=seeded["seed"], numpy_version=seeded["numpy_version"])
        for k in ("mean", "lower", "upper"):
            assert got[k] == pytest.approx(v["seeded"][k], abs=seeded["tolerance"], rel=0), (v["id"], k, got)
        assert analysis.correctness_verdict(got["mean"], got["lower"], got["upper"]) == v["seeded"]["verdict"]
        assert v["seeded"]["verdict"] == v["verdict"]


def test_the_governing_draws_are_reproducible_from_the_seed():
    needs_numpy()
    counts = VECTORS["vectors"][0]["counts"]
    first = analysis.governing_interval(counts, seed=7, draws=50_000, numpy_version="2.4.6")
    assert analysis.governing_interval(counts, seed=7, draws=50_000, numpy_version="2.4.6") == first
    assert analysis.governing_interval(counts, seed=8, draws=50_000, numpy_version="2.4.6") != first


def test_the_convolution_crosscheck_agrees_with_the_draws():
    needs_numpy()
    plan = draft_plan()
    for i, v in enumerate(VECTORS["vectors"]):
        drawn = analysis.governing_interval(v["counts"], seed=i, draws=250_000, numpy_version="2.4.6")
        exact = analysis.exact_interval(v["counts"], bins=200)
        for k in ("mean", "lower", "upper"):
            assert abs(drawn[k] - exact[k]) <= plan["crosscheck"]["tolerance"], (v["id"], k, drawn, exact)


def test_the_simulation_reproduces_the_designer_dry_run_within_monte_carlo_error():
    # Q7 §13.3: on the designer's raw vector at 12 runs per arm, about 81% CORRECTNESS_BETTER at +20 points, 94% at
    # +25, 5-6% at the null, and 80% CORRECTNESS_WORSE at -20. The tool runs 2,000 replicates of 10^6 draws; this runs
    # 300 of 4,000, and allows 3.5 Monte Carlo standard errors plus 2 points for the dry run's own "approximately".
    needs_numpy()
    plan = draft_plan()
    expected = {"+20": (analysis.BETTER, 0.81), "+25": (analysis.BETTER, 0.94), "null": (analysis.BETTER, 0.055),
                "-20": (analysis.WORSE, 0.80)}
    result = analysis.simulate(plan, replicates=300, draws=4000,
                               scenarios=[("designer-dry-run", e) for e in expected])
    assert result["full"] is False and result["replicates"] == 300
    for row in result["scenarios"]:
        verdict, target = expected[row["effect"]]
        rate = row["rates"][verdict]["rate"]
        allowed = 3.5 * math.sqrt(target * (1 - target) / 300) + 0.02
        assert abs(rate - target) <= allowed, (row["effect"], rate, target, allowed)
        assert sum(r["rate"] for r in row["rates"].values()) == pytest.approx(1.0)
    # A scenario's stream depends only on the seed and its own index, so running it alone gives the same verdicts.
    alone = analysis.simulate(plan, replicates=300, draws=4000, scenarios=[("designer-dry-run", "+25")])
    assert alone["scenarios"][0] == next(r for r in result["scenarios"] if r["effect"] == "+25")
    analysis.validate(analysis.SIMULATION_SCHEMA, result, what="the simulation record")   # PR #188 review, n4


def test_a_scored_campaign_gets_one_correctness_and_one_cost_verdict():
    needs_numpy()
    plan = draft_plan()
    plan["cost"]["ceiling_ratio"] = 2.5
    plan["cost"]["bootstrap"]["replicates"] = 200
    rows = campaign(plan, [10] * 6, [5] * 6)
    record = analysis.analyze(plan, rows, [], recon(plan, rows))
    assert record["headline"] == f"{analysis.BETTER} / {analysis.WITHIN}"
    assert record["correctness"]["draws"] == analysis.DRAWS
    assert record["u3"]["flag"] is False
    assert set(record["safety"]) == {"A", "R", "R+", "events"}
    assert set(record["secondary"]["A"]["f4"]) == set(plan["cells"]["f4"].values())
    assert record["descriptive"][plan["cells"]["primary"][0]]["R+"] == {"accepted": 3, "n": 5}
    assert record["cost"]["bootstrap"]["undefined"] == 0
    assert record["cost"]["bootstrap"]["lower"] <= record["cost"]["ratio"] <= record["cost"]["bootstrap"]["upper"]
