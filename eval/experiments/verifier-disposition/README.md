# Verifier-disposition rehearsal

The decision this experiment is built for: does exposing the shipped `acceptance-verification` skill to a verifier improve its **first** disposition (accept or rework) enough to justify the extra context? Both arms get the same tree, so a grader driven by the final tree cannot answer it. The observable is the verifier's emitted decision and the evidence behind it, bound to the submitted candidate.

**This directory does not measure that effect.** It qualifies the instrument on public cases with a scripted verifier, no model, no provider and a preregistered budget of zero. The scripted verifier decides from fixed checks and ignores the skill, so its grades carry no information about the skill. Evidence of effectiveness needs separately approved model attempts (per-role release qualification and enforced spend limits first) and fresh private variants in `aew-private/eval/`, neither of which is included here. These public cases are development material; their results qualify the instrument and never decide adoption.

## The preregistration

`plan.yaml` (experiment `verifier-disposition-offline-1`, `purpose: qualification`) freezes two scripted arms that differ only in skill exposure:

| Arm | Role projection | Skill exposure |
| --- | --- | --- |
| `inaccessible` | the shipped verifier card with `skills: []` (experiment-local) | none: nothing is copied, so the `skill` tool has nothing to list |
| `exposed` | the shipped verifier card, unchanged | `acceptance-verification`, at its manifest hash |

Everything else is identical: the case task, the candidate tree, the probe and the checks. Each run records the projection it applied (the card's hash and the applied card's hash) and the exposure AEW's own skill copy (`aew.skills.deliver`) actually delivered. The adapter refuses to count a run whose delivered exposure is not its arm's. `scoring.rubric_sha256` commits to the evaluator's expected decisions before any run.

## The cases

Each case is the M3 ledger project (`fixture/base`, a byte-for-byte copy of `eval/m3/dogfood/fixture/base`) with one submitted candidate for the M3 T5 Ticket, "Add split_amount()". All three cases share the same task, the Ticket's goals and the implementer's report. Every candidate passes its own tests.

| Case | Candidate |
| --- | --- |
| `VD-CLEAN` | the M3 T5 reference with focused tests |
| `VD-T5` | the M3 T5 seeded first attempt: equal rounded shares that do not add up |
| `VD-REPAIR` | a plausible repair: the shares now add up, but the leftover cents go to the last shares instead of the first |

Only the base, the case's candidate and the task enter the verifier's repository. Case ids and `evaluator/` never do. T5 is a calibration control. In M3, review caught it in four of four runs, and the raw comparison fixed it four of four times, so it cannot by itself show an incremental benefit.

## The adapter and the grader

`disposition_adapter.py` is public and holds no answers. It takes the first `kind: verification` record a run emitted, before anyone repairs the candidate. `accept` is exactly what AEW's verification gate passes; everything else is `rework`. A missing or malformed record is a counted `no_disposition`. It records separately each claim the observed checks do not support: no check cited, a check never observed, one observed on another snapshot, or one that contradicts the claim. It also records edits to the candidate (an authority violation) and the attempt's cost, where absent means unmeasured, never zero. An exposure other than the arm's, or a record bound to another snapshot, makes the run `invalid`.

`evaluator/disposition_grader.py` is evaluator-only. It grades an observation only after `blind()` has removed the arm and its exposure: `correct_accept`, `justified_rework`, `false_accept` or `false_rework`. Unsupported claims and cost are carried beside the grade and never change it. Runs use neutral names, so the run id does not name the arm either.

`scripted_verifier.py` runs the project's tests, a goal probe (`probe.py`, derived from the Ticket's goals alone) and a scope check against the delivered candidate without writing to it. It emits one `aew/evidence/v1` verification record whose claims cite those checks.

## Reproduce

```sh
python -m pytest -q tests/unit/test_eval_verifier_disposition.py tests/integration/test_eval_verifier_disposition_rehearsal.py
python -B eval/experiments/verifier-disposition/evaluator/calibrate.py
```

The integration test freezes the preregistration and runs all six cells through F19's runner. It checks that both arms of each case received the same candidate bytes and that the projections differ in the skill list alone. Only the exposed arm's run folder holds the skill, at its manifest hash. The candidate stayed untouched, and the blinded grades match the expected dispositions in both arms. The calibration is described in `evaluator/README.md`.

## Not yet built

- A verifier dispatched through AEW and launched by the OpenCode adapter, as the context-pack rehearsal did for the implementer, so that the applied projection is read back from the served agent.
- The model arm's exposure trace: whether the verifier actually loaded the skill (`loaded`), from the session's tool calls. This keeps availability apart from selection (skill evaluation guide §3).
- Fresh private variants and the approved model attempts that a decision needs.
