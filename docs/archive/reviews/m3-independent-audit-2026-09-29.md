# M3 independent audit: temporal boundaries and intent fidelity

**Scope.** Read-only review of `impl/m3-opencode`, starting at `e6ab7cb` and rechecked after the existing audit was committed as `38ecce1` on 2026-09-29. This is a companion to [the M3 audit findings](m3-audit-findings.md), not a second pass over its CI, Lead-cost, documentation, and mixin findings. No product code was changed. I inspected the engine's check-evidence path, the check subprocess runner, the OpenCode adapter and supervisor, the `--fields` parser, related tests, and the relevant design text. I used disposable projects or in-memory probes for the reproductions below. I did not run a live OpenCode session or repeat the full suite.

The recurring pattern is a **time boundary**: AEW correctly records or checks a fact at one instant, then treats it as valid after the policy, process tree, or prompt stream has changed. The strongest architecture work for M3 is to make those boundaries explicit. The table is ordered by risk to the current M3 claims, not implementation effort.

| ID | Finding | Severity | Suggested disposition |
|---|---|---|---|
| I1 | A passed local check stays `CURRENT` after that check's command changes under the same ID | High | Fix or explicitly constrain policy changes before independent review |
| I2 | A timed-out check can leave a child process running after evidence is recorded | High | Fix before independent review |
| I3 | An accepted Lead `harness send` can race an old idle result and end the run | Medium | Fix before independent review; fake-server regression |
| I4 | The effective-model check reports `match` for requested high effort and observed default effort | Medium | Fix before independent review |
| I5 | `--fields` guidance promises literal text, but unquoted YAML can truncate it and duplicate keys can overwrite it | Medium | Parser rejection and guidance before review |

## I1. Local check evidence is not bound to its check definition

`check_run` resolves the command from current `.aew/policy/checks.yaml`, runs it, and records the command in evidence ([`evidence_ops.py`](../../../src/aew/engine/evidence_ops.py#L426-L475)). But the `local_checks` gate selects evidence by `check_id`, evaluated-workspace fingerprint, and plan revision; it does not compare the recorded command or a digest of the check definition with the current policy ([`gates.py`](../../../src/aew/engine/gates.py#L103-L119), [gate selection](../../../src/aew/engine/gates.py#L151-L159)). The evaluated snapshot intentionally excludes `.aew` policy files ([ADR-0002](../../implementation/adr/0002-evaluated-snapshot-fingerprint.md)).

**Reproduction.** In a disposable project, I ran the configured `unit` check and got a passing `INV-0001-check-unit-1`. I then changed only `unit.command` in `.aew/policy/checks.yaml` to `[{python}, -c, raise SystemExit(1)]`, expressed as three YAML list entries. The work fingerprint was unchanged and `gate show` still returned `local_checks: CURRENT`, citing the old evidence ID. No new check ran. This lets a check ID stand for two different acceptance conditions; a Lead can proceed using evidence for the former one.

The design choice is whether an in-flight Ticket pins its check policy or must satisfy the newest policy. Either can work, but the gate must say which definition the evidence proves. Record a canonical check-definition digest with each check result and compare it at gate evaluation, or pin the policy version to the Ticket and show that pin. A changed command should yield `STALE` or a clearly reported policy mismatch. Add a regression that changes a command without changing source files or plan revision. The existing source-staleness tests do not cover this boundary.

## I2. Check timeout ends the direct process, not its descendants

The runner uses `subprocess.run(..., timeout=...)`, catches `TimeoutExpired`, and returns a failed result ([`checks.py`](../../../src/aew/policy/checks.py#L33-L49)). `subprocess.run` kills and waits for its direct child on timeout; it does not own that child's descendants. `check_run` then immediately takes its after-snapshot and writes evidence ([`evidence_ops.py`](../../../src/aew/engine/evidence_ops.py#L445-L485)). This path is used by the M3 bridge as well as direct check calls; it does not register the check in the harness's process tree.

**Reproduction.** With a 0.15-second check timeout, the check's parent spawned a child that slept 0.8 seconds and then wrote a marker outside the disposable workspace. AEW returned `exit_code: None`; 1.2 seconds later the marker existed and contained `child continued`. The marker was removed after the probe. A descendant could instead write inside the workspace after AEW has taken the after-snapshot, so the evidence's snapshot need not describe the final side effects of that check.

Launch each check in a platform-appropriate process group or job object, terminate and drain its entire tree on timeout/cancellation, and only then take the after-snapshot. Test a child that writes after its parent times out, on both Windows and Linux. This is a process-lifetime gap, separate from the broader sandbox-containment limitation already tracked in future work.

## I3. Lead send and turn completion have a race

The adapter records a new prompt ID and sets `turn = "running"` under a lock before posting it ([`adapter.py`](../../../src/aew/harness/opencode/adapter.py#L276-L298)). Its poller also uses the lock to confirm that the last sent ID still precedes an idle event, but releases the lock before calling `_turn_over` ([`adapter.py`](../../../src/aew/harness/opencode/adapter.py#L375-L410)). `_turn_over` takes a snapshot before `_end` unconditionally marks the turn ended ([`adapter.py`](../../../src/aew/harness/opencode/adapter.py#L412-L431)). A Lead send between the poller's last check and `_end` can therefore be accepted by OpenCode and then overwritten by completion of the previous turn. The supervisor stops watching an adapter that is no longer alive.

**Reproduction.** An in-memory adapter probe paused `_turn_over` after the poller's last check. During the pause, `send("lead continuation")` appended a second prompt ID and set `turn` to `running`. Resuming the old idle finalization changed `turn` to `ended` with both IDs still in `sent`. The fake client accepted the send. This proves the interleaving in AEW code; it does not establish its frequency against a live V2 server.

Carry a monotonic prompt generation or the last prompt ID from `_poll` into `_turn_over`, then revalidate it under the lock immediately before changing the terminal state. If a newer prompt exists, keep the run alive. Add a deterministic barrier test using the fake V2 server and, if available, a live smoke check. The check must cover a send during `_take_snapshot`, which widens the current race window.

## I4. The model pin check treats default effort as a match

The adapter's effective-model record represents a missing, empty, or `default` variant as `effort: None` ([`adapter.py`](../../../src/aew/harness/opencode/adapter.py#L535-L546)). The supervisor compares effort only when effective effort is not `None` ([`supervisor.py`](../../../src/aew/harness/supervisor.py#L309-L327)). Therefore a run requested with `effort: high`, but reported by the adapter with the same provider/model and `effort: None`, gets `model_check.status: match` and an empty `mismatches` list. I reproduced that exact record through `_compare_effective` in memory.

If `default` is an observed variant, it should differ from requested `high`. If the API truly omits the variant and effort cannot be observed, report `unknown` or `unreported` rather than `match`. Preserving that distinction at the adapter boundary would avoid conflating an explicit default with absent telemetry. Add tests for both forms. This is a reporting and assurance error; the probe does not show that OpenCode actually ignored a high-effort request.

## I5. `--fields` protects shell text, but its YAML layer can change authored text

The new `--fields` route protects values from shell expansion, which addresses the M3 dogfood defect. Its documentation and help say values are applied *literally* and that every scalar stays the exact text written ([`fields.py`](../../../src/aew/cli/fields.py#L1-L8), [`quickstart.md`](../../guides/quickstart.md)). The parser uses `yaml.BaseLoader`, which preserves scalar types as strings but still applies YAML comments, quoting, and mapping rules ([`fields.py`](../../../src/aew/cli/fields.py#L78-L89)). In a direct parser probe, `goal: Finish #1 with $5.00` became `Finish`; `goal: first` followed by `goal: second` became only `second`. A quoted shell heredoc does not prevent either transformation. The Lead prompt recommends natural `title: ...` and `goal: [...]` YAML forms ([`projection.py`](../../../src/aew/harness/opencode/projection.py#L175-L181)).

Keep the YAML/JSON input if it is useful, but describe it as parsed data rather than byte-exact prose. Show quoted or block-scalar examples for free text containing `#`, `: `, or significant whitespace; JSON is another safe example. Reject duplicate mapping keys, including keys that normalize to the same CLI option (`foo_bar` and `foo-bar`). Add parser tests for those cases and one end-to-end test that compares the submitted text with the authored intended value. This is an intent-fidelity risk rather than another shell-injection defect.

## Architecture and efficiency implications

The existing audit identifies Lead command count as the dominant measured cost and correctly leaves compound workflow operations to the designer. My review suggests an additional prioritization rule: first make each operation's **receipt and validity window** explicit, then combine them. A combined transition-and-dispatch command would reduce model steps, but it should return the new revision, the next action, and a run-delivery receipt that distinguishes *requested*, *accepted by the adapter*, and *completed*. Today a `harness send` request can be accepted yet lost at the adapter boundary (I3). A single precise result shape would also reduce status reads without obscuring gates.

Check evidence needs the same precision: include the policy version it proves (I1), the process-tree outcome and settled after-snapshot (I2), and an explicit `unknown` where effective execution cannot be observed (I4). These are small local contracts across existing components, not a case for restructuring all 13 Engine mixins during M3. They also provide sharper regression targets than another broad end-to-end suite.

**Limits and validation.** The I1, I2, I4, and I5 behaviors were reproduced in disposable or in-memory probes; I3 was a deterministic interleaving probe, not a live-server observation. The separate audit's full-suite result at `e6ab7cb` was not rerun here. The targeted adapter, intent-ingress, evidence-gate, and OpenCode unit suites passed: **85 passed in 322.21 seconds** (`pytest ... -q -p no:cacheprovider`). These tests establish the current baseline; they do not contain regressions for the findings above.
