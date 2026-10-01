# Response to the independent M3 audit (2026-09-29)

- **Audited branch:** `impl/m3-opencode` at `e6ab7cb`, rechecked at `38ecce1`.
- **Audit:** [`m3-independent-audit-2026-09-29.md`](m3-independent-audit-2026-09-29.md), by the designer: temporal boundaries and intent fidelity, findings I1 to I5. It is a companion to the read-only [M3 audit](m3-audit-findings.md).
- **Disposition (operator and designer, 2026-09-29):** all five fixed before the M3 independent review. One design decision was needed (I1) and was taken: option (a).
- **Spec set:** `aew-frozen-2026-09-25`, unchanged. No finding is a frozen-contract contradiction. Each is a fact checked at one moment and then trusted after the policy, the process tree or the prompt stream had changed, as the audit put it.

Every regression is in `tests/regression/test_m3_independent_audit.py`. Each was written first and seen failing, for the reason the finding gives, before its fix.

## Findings

| ID | Finding | Fix | Commit |
|---|---|---|---|
| I1 | A passed check stayed `CURRENT` after the check's command changed | Decision (a): an in-flight Ticket satisfies the check as defined now. Each check result records `check.definition_sha256` (command, working directory and timeout; for guardrails, its policy; a description is not part of it). `local_checks` counts only results for the current definition, and a pass for an earlier one is `STALE` with its reason. ADR-0002 amended. | `ecd4a13` |
| I2 | A timed-out check could leave child processes running after its evidence was sealed | Checks run in their own process tree: a job object on Windows, a process group on POSIX. On timeout the whole tree is killed; when the check returns, anything it left running is ended and waited for, and the log says so. The engine's after-snapshot therefore follows every process the check started. | `880ce88` |
| I3 | A Lead `harness send` could race the end of a turn and be lost | Closing a turn re-checks, under the lock, that no newer prompt arrived since the poll decided; if one did, the run continues. | `1094fb8` |
| I4 | A requested `high` effort, with the default or an unreported effort observed, was recorded `model_check: match` | OpenCode's explicit `default` variant stays `effort: None` (an observation); a missing or empty variant is marked `effort_unreported`. Effort is always compared unless unreported: `high` against the default is a `mismatch`, and a requested effort that cannot be observed gives the new status `effort_unreported`, never `match`. | `d25e44d` |
| I5 | `--fields` promised literal text, but YAML comments could truncate it and duplicate keys overwrite it | The mapping is walked node by node, and every form that would silently change authored text is refused with a hint to quote the value, use a block or JSON. The documentation and the Lead's system text no longer call the input literal; the Lead's examples now use single-quoted values. | `0069676` |

## Where the fixes go beyond the audit's suggestions

- **I1** applies the same rule wherever a check result counts: to policy-required post-integration checks at publication, and to checks a verifier cites (refused at `submit` if run under a definition since changed). **Boundary:** a verification report already ingested stays ingested when a definition later changes. The Ticket still cannot proceed on it: its own `local_checks` goes `STALE` and must be re-run before COMMIT_READY and publication (ADR-0002 amendment).
- **I2** also ends processes a check left running after its parent exited *normally*, since they could change the workspace after the snapshot just the same.
- **I3** has a second ordering, found while writing its regression. A `send` arriving just *after* the turn ended set the turn back to "running", although the adapter's watcher had already stopped. The run then looked alive, nothing watched it, and it would have hung until its deadline, or forever without one. Such a `send` is now refused (`HarnessError`); the supervisor records it as `request_failed`, and nothing reaches OpenCode.
- **I5** refuses more than the two cases the audit reported. Probing found four more ways the YAML layer changed text silently: anchors (`&1 is the first case` became `is the first case`), aliases, tags (`!x value` became `value`), and an unquoted value continued on another line (the line break became a space). Double-quoted escapes are kept, because they are how JSON writes backslashes and quotes, and JSON is the recommended safe form; the guidance says so.
  - A YAML syntax error now says where it is and how to fix it. In the dogfood, 5 of the Leads' 89 `--fields` inputs had failed on a key indented by one space, with YAML's bare "mapping values are not allowed here".
  - **Checked against the dogfood:** all 89 real `--fields` inputs from the paid Lead sessions parse to exactly the values the old parser gave, or were refused by both (those 5). None had been silently changed, and none of the new refusals would have rejected an input the dogfood accepted.

## Also found and fixed on the way (not in the audit)

The first CI run on M3 (PR #5) found two failures the local runs had not:
- **M3-D11,** a real race in the Lead broker. A Lead session that ended while the broker's watchdog was mid-check could be reported "superseded", because `close()` cleared the credential under the check. The check now takes the credential before reading state, and `close()` waits for it (`6a45c5d`). This was the step-3 failure that the M3 audit had attributed to overload.
- **A race in the fake OpenCode server,** a test helper: it reported a turn idle before saving it (`c566c16`).

CodeQL's 68 new alerts were all the intended use of operator-run scripts in `eval/`, or of paths the operator chooses. `eval/` is now excluded from code scanning through a repository workflow (`f643bd0`).

## Validation

- **Local:** the full parallel suite after I1, then after the audit's X1, X2 and A2 fixes: 981 passed and 984 passed, each with the 4 pinned platform skips; the serial lane is green. The regressions also pass on Linux (WSL, Python 3.11).
- **CI:** green on both operating systems through I5 (20 of 20 checks). The run after I1, X1, X2 and A2 is in progress when this is written.
- **Not validated live.** The live lane against real OpenCode was not rerun for these fixes. I3 and I4 change the adapter's end-of-turn and model-check logic; both are covered deterministically by the fake V2 server and the in-memory regressions.

## Decisions an operator should confirm

- **I1: option (a),** taken by the operator on 2026-09-29. The alternative was pinning each Ticket's check policy at dispatch.
- **I4: the status name.** The audit suggested `unknown` or `unreported`. `effort_unreported` is used, because `unreported` already means the harness reported no models at all.
