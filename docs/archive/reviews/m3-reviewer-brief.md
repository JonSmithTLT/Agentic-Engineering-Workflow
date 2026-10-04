# M3 independent review brief

**For:** the independent reviewer(s) of AEW M3, before M4 begins.
**Branch:** `impl/m3-opencode`, from `main` at `adef640` (M2 accepted and merged, PR #4). **Frozen specs:** WC v0.7, KC v0.4, SPT-R v0.2 (`aew-spec-frozen-2026-09-25`, unchanged).
**Pending when this brief was written:** the operator's own TUI session (M3 plan §9). Its result will be added here: _pending_.
**Audits before this review:** a read-only audit ([`m3-audit-findings.md`](m3-audit-findings.md)) and the designer's independent audit ([`m3-independent-audit-2026-09-29.md`](m3-independent-audit-2026-09-29.md)). The findings the operator and designer chose to fix before this review are fixed; the response, with every commit and regression, is [`review-response-2026-09-29.md`](review-response-2026-09-29.md). The rest are tracked in `future-work.md` §6.

## What M3 claims

1. **Harness independence.** AEW attaches a real agent harness (OpenCode V2 2.0.18) behind a narrow, harness-neutral adapter contract. AEW still holds the workflow, knowledge, authority, evidence and resumable state. OpenCode's state is disposable: destroying it loses a conversation, never the project.
2. **Runs.** Each harness execution of an invocation is a run `R-<INV>-<n>` in control state. Relaunching rotates the invocation's credential in the same commit, so at most one run can act. Harness loss is not INTERRUPTED (M3-B1).
3. **Credential custody (operator requirement).** No raw AEW credential, invocation or Lead, ever enters a model-controlled process. Agents act through run-scoped bridges; the Lead acts through a broker. The engine's own authority checks stay authoritative; the bridges add no authority.
4. **Execution profiles.** Harness, provider, model and effort are policy, pinned per invocation at dispatch and stamped on evidence by the engine. The harness's effective model is checked against the pin.
5. **Harness state never moves AEW state.** A run's end, success or crash changes nothing. Only the Lead's ingests, transitions and decisions do (WC §8.2).
6. **M1 and M2 are unchanged.** Every M1/M2 test, reviewer probe, walk and AT-1..AT-13 passes unchanged. Schema changes are additive. Dispatch output is unchanged without `--launch`. Packs are unchanged.
   - **One M1 rule is tightened** (independent audit I1, ADR-0002 amendment): a check result proves only the check definition that ran, so changing a check's command makes earlier results for it `STALE`. Before, they stayed `CURRENT`.

The approved plan is `m3-ambiguity-report.md`. The decisions are ADR-0009 (harness boundary, runs, custody, the OpenCode adapter) and ADR-0010 (execution profiles), with amendments to ADR-0005 (custody and rotation), ADR-0006 (skills and capabilities as projection) and ADR-0001 (step 7, performance). The OpenCode V2 facts are in `m3-opencode-v2-rebaseline.md`.

## How to read the evidence

Keep these apart; the documents label which is which.

| Kind | What it proves | Where |
|---|---|---|
| **Contractual invariants** (frozen specs, oracle-checked) | Authority, evidence, gates and state behave as specified whatever the harness does | the oracle (`tests/helpers/invariants.py`, rules 1–18), AT-1..AT-17, the adversarial regressions |
| **AEW implementation choices** (ADR-level, changeable) | The custody bridge's design, run records, rotation, the curated environments, the projection | ADR-0009, ADR-0010; unit and integration tests |
| **OpenCode-specific behaviour** (V2 facts, may drift) | What 2.0.18 actually does: `serve --stdio`, permission ordering, `PUT /environment`, asynchronous catalogs | `m3-opencode-v2-rebaseline.md`; the capability probe at every launch; the live lane |
| **Deterministic evidence** | The properties, asserted, with scripted models | CI: fake harness, and the real adapter against a fake V2 server serving the real 2.0.18 API description |
| **Real-model evidence** | What happens with real models: invariants asserted, outcomes *recorded* | step 8 (`harness-conformance.md` §6, free models), step 9 (`m3-dogfood-report.md`, paid) |
| **Future-milestone functionality** | Not claimed by M3 | `future-work.md` |

Real-model evidence is small (47 dogfood runs, plus the step-8 trials) and on small tasks. It shows the machinery working with real models; it does not establish rates.

## Where to look

| Area | Code |
|---|---|
| Adapter contract, launch contract, run status | `src/aew/harness/base.py`, `contract.py` |
| Run supervisor: custody, watchdog, deadline, collection, post-run credential scan | `src/aew/harness/supervisor.py` |
| Custody bridge (JSON only, HMAC key challenge, typed operations, redaction) and CLI routing | `src/aew/harness/bridge.py`; routing in `src/aew/cli/commands.py` |
| Lead broker (`aew lead session`), `lead.cli` and `lead.whoami` | `src/aew/harness/lead_broker.py` |
| Agent environment allowlist | `src/aew/harness/agentenv.py` |
| Process-tree ownership (Windows job object, POSIX group plus sentinel) | `src/aew/harness/procs.py` |
| Run records (local telemetry) | `src/aew/harness/runlog.py` |
| Runs, rotation, launch preconditions, `harness status/wait/stop/send/interrupt` | `src/aew/engine/harness_ops.py`; `rotate_invocation_token` in `src/aew/engine/authority.py` |
| Evidence stamping, `WORKSPACE_MUTATED` (M3-B6) | `src/aew/engine/evidence_ops.py`; `ENGINE_OWNED_PRODUCER` in `src/aew/knowledge/evidence.py` |
| Execution policy and pin | `src/aew/policy/execution.py`; `_new_invocation` in `src/aew/engine/workspace_ops.py` |
| OpenCode adapter: HTTP client, health and capability probe, projection, Lead TUI | `src/aew/harness/opencode/{client,capabilities,adapter,projection,lead}.py` |
| `resume` with runs and session authority (M3-D10) | `src/aew/engine/resume_ops.py` |
| `--fields` ingress (companion review B1) | `src/aew/cli/fields.py`, `src/aew/cli/main.py` |
| Performance (step 7): libyaml, parse reuse by SHA, profiling | `src/aew/util.py`, `src/aew/engine/store.py`, `src/aew/profile.py` |

M3 touched 46 source files (+4,540 / −85 lines). Outside `src/aew/harness/` and the new files, the changes to M1/M2 code are small and additive: `evidence_ops.py`, `resume_ops.py`, `store.py`, `work_commands.py`, `commands.py`, `authority.py`, `workspace_ops.py`, `nonmutating_ops.py`, the schemas, and profiling hooks in `lock.py`.

## Invariants to attack

The oracle checks rules 1–16 (M1, M2) unchanged, plus:

| # | Invariant |
|---|---|
| 17 | No evidence postdates the revocation of the credential that produced it, rotation included |
| 18 | Runs are numbered in order; at most one run per invocation holds live authority, and only the latest; while the invocation is active, its latest run holds its credential |

Enforced by operations and covered by tests, not by the oracle:
- the five custody properties, invocation and Lead side (`harness-conformance.md` §3; AT-17);
- the bridge's re-check of its run's authority before each request, and the engine's re-check under the control lock;
- `WORKSPACE_MUTATED` for reviewers and verifiers;
- health failing closed (`HARNESS_INCOMPATIBLE`);
- relaunch preconditions (`RUN_LIVE`, pack regeneration to the pinned sha).

## Highest-risk areas (please attack these first)

1. **Custody bypass and capability leakage.** Any path by which a raw credential reaches a model-controlled process, a file it can read, the harness database, or command output. Any bridge operation that does more than the invocation's archetype allows. The Lead broker's refusal list and redaction.
2. **Dependence on undocumented or experimental OpenCode surface.** `serve --stdio` is undocumented; the session, permission and event APIs are tagged experimental and V2 has no stability policy. The capability probe is meant to fail closed on drift within V2: check that it covers what the adapter actually uses.
3. **Session permission override semantics.** AEW relies on V2 applying session-create permissions last. An `ask` anywhere would block forever. Check that no rule the adapter sends can be overridden, and that nothing reopens `subagent`, `question` or `external_directory`.
4. **The agent reaching its own server API.** `serve --stdio` strips `OPENCODE_PASSWORD` from its own environment; AEW also never gives the agent the password. Look for other routes.
5. **Process-tree escape.** Job-object breakaway, out-of-tree spawners (services, scheduled tasks), POSIX `setsid`. Authority is unaffected by an escaped process (its credential is dead), but check that claim too.
6. **Rotation races.** A request in flight across a rotation, a check spanning one, a woken old supervisor. The pause points (`AEW_PAUSE`) make these deterministic in the existing tests.
7. **M3-B6 and its fix.** A reviewer or verifier editing the shared live workspace.
8. **Run records are model-writable** (same user). Nothing that decides anything may read them; `harness status`, `wait` and `resume` read evidence from the store.

Suggested probes:
- a revived old session (copied state, old bridge coordinates) trying `submit`, `check run` and `whoami`;
- a model that writes a project `opencode.json`, `.opencode/` or `AGENTS.md` into its workspace;
- a pickle or oversized payload to either bridge; a request naming another invocation or run;
- a doctored `/openapi.json` or model catalog;
- a Lead command through the broker that emits a credential through an unusual path (error text, `--help`, a JSON field);
- a relaunch racing an ingest; a takeover while a run is mid-submit;
- `aew resume` after `.aew/local` is wiped with runs live;
- **plan assurance binding** (ADR-0006 amendment 2026-09-30): a plan-bound review or verification removed without a new plan revision (staff, forbid, a racing plan accept, an adopted Planner proposal), or a stale binding surviving supersession.

## Found and fixed during M3

Each with a regression written before the fix:
- M3-D1: M2's executor dispatch pinned its pack before the attempt's output contract was recorded (pre-existing; found by the launch preconditions);
- M3-B6: reviewer and verifier edits of the shared workspace were caught only at ingest, as "stale", with no author;
- run records could be rewritten by a later run, and `harness status` showed forged evidence lists (display only; no state moved);
- M3-D2 to M3-D7, found by live free models (step 8): Windows text encodings, the event log's tool names, stale evidence in a continuation, a malformed section crashing `submit`, no scratch directory, resolved findings checked too late;
- M3-D8 to M3-D10, found by the paid dogfood (step 9): the next action after an implementer run, a comma inside a scope glob, `resume` inside a Lead session;
- three performance pathologies (step 7, `m3-performance.md`);
- M3-D11, found by the first CI run: a Lead session ending while the broker's watchdog was mid-check could be reported "superseded";
- the designer's independent audit, I1 to I5: a check result bound to its definition, a check's whole process tree ended before its evidence is sealed, a Lead message racing a turn's end, an effort that cannot be observed never reported as a match, and `--fields` input that YAML would silently change refused (`review-response-2026-09-29.md`);
- from the read-only audit: refusals and `resume` next actions that name the command that applies (X1, X2), and `aew doctor` reporting the YAML backend (A2).
- from the operator's TUI acceptance session (2026-09-30) and the Lead's debrief: an accepted plan's promised review and verification now bind as required gates (ADR-0006 amendment 2026-09-30); contradictions between the policy files are reported in `doctor`, next actions and at the gate (`aew.policy.consistency`); next actions no longer offer check results for `ingest`; each role's briefing names only the `aew` commands it may use (`test_uat_2026_09_30.py`; `future-work.md` §7).

The companion design review (2026-09-28, `m3-companion-review-triage.md`) was triaged into M3 blockers and post-M3 prerequisites. The three blockers were done before the dogfood resumed: B1 authored text as data (`--fields`), B2 the `workdir_separation_only` containment label, B3 failure names from the registry.

## What the dogfood showed (`m3-dogfood-report.md`)

- Plain OpenCode passed 20 of 20; AEW 24 of 26 (Sol 12 of 12) at about 7× the cost and time. The Lead was about 40% of AEW's cost.
- AEW's value, as measured: resume after losing the Lead's harness (3 of 3), independent review catching a seeded defect (4 of 4, and 6 of 6 in the model comparison), investigation Tickets.
- **One run where AEW was worse** (T4, Luna): the Lead turned an operator's wrong hypothesis into goals, put the data those goals were measured against into scope, and the implementer met the goal by editing the data. Review and two verifications passed it. Every mechanism behaved as designed; the failure is upstream of all of them. The designer's response is the plan assurance design (`docs/archive/superseded/plan-assurance-and-premise-validation-design-v0.3.md`, `future-work.md` F14), which is post-M3.
- The tasks were too easy for either mode to fail, so AEW's quality claim is untested.

## How to run

```bash
python -m pytest -q -n auto -m "not serial" && python -m pytest -q --lane serial   # full suite
python -m pytest -m acceptance -q                                                   # AT-1..AT-17
python -m pytest tests/regression/test_m3_harness_adversarial.py tests/integration/test_harness_runs.py \
                 tests/integration/test_lead_session.py tests/integration/test_opencode_adapter.py -q
python -m pytest --live tests/live -n 4 -q        # opt-in: real OpenCode 2.0.18, a free model (see opencode.md)
```

Last full results (after the audit fixes, 2026-09-29): Windows 984 passed with the 4 pinned platform skips, plus the serial lane. CI (`assurance`, Linux and Windows) is green on PR #5 through the independent audit's I5; see the PR for the latest run. Live lane on 2.0.18: 25 passed, 1 skipped by design (step 8; not rerun for the audit fixes, which the fake V2 server and in-memory regressions cover). Every M1 and M2 reviewer probe file runs unchanged.

## Known limits (Staged / Designed, not defects)

- **Containment is workdir separation only** (`AEW-INV-ISO-001`). An agent's shell runs as the operator and can read and write anything the operator can. Every run is labelled, `aew doctor` warns, and nothing claims more. Real containment gates real-repository use (`future-work.md` F2).
- **The same-UID threat model is unchanged** (ADR-0005). Custody closes the accidental and persistent exposure paths, not a deliberate same-user memory read on Windows. On Linux the supervisor is non-dumpable.
- **One harness, one version, one OS for real runs:** OpenCode 2.0.18 on Windows. Linux is covered by CI against a fake V2 server.
- **No skills.** Card skills are reported unavailable (WC §16.10); skills arrive through the capability registry (`future-work.md` D3, F12, F13).
- **`subagent` is denied** for every role, and foreign sessions are recorded.
- **Serial mutation**, as before (cap 1 until M4/M5).
- **Control-state cost is linear in history.** `control.yaml` grows about 20 KB per DONE Ticket. Hot/cold archival (ADR-0011) is the accepted direction, and **implementing and accepting it is a prerequisite for M4**, after this review. Its thresholds await the designer (`future-work.md` Q1, Q2).
- **Plan quality is not checked before implementation.** Only the Lead accepts plans, and goals are first examined by the verifier. See the dogfood's T4 and `future-work.md` F14.

Everything designed but not built, with its gate, is in `future-work.md`.
