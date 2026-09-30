# M3 read-only audit: findings

**What this is:** a read-only pass over the M3 branch (`impl/m3-opencode` at `e6ab7cb`) after step 10's docs, requested by the operator on 2026-09-29. It covers architecture, CI and CD, testing, the Lead's cost, and the friction that live and dogfood runs exposed. **No code was changed.**

**Evidence used:** the code; `.github/workflows/`; `tests/durations.json`; a full local parallel suite run with timings (§3); and the step-9 dogfood records (`eval/m3/dogfood/results.jsonl`, the 26 AEW runs on the hardened code, 29 Lead sessions), re-analysed for this audit.

**Dispositions:**
- **Before review:** small and low-risk. Worth doing before the M3 independent review, with the operator's go-ahead.
- **Post-M3:** real work, not needed for M3's claims. Belongs in `future-work.md`.
- **Designer:** a design or policy choice.

## Summary

| # | Finding | Severity | Disposition |
|---|---|---|---|
| C1 | CI has never run on any M3 commit: the branch was never pushed | **High** | Before review |
| C2 | CI shard sizes come from M2 timings, with no M3 tests in them | Medium | Before review (with C1) |
| L1 | The Lead's cost comes from step count, not waiting: a median 20 of 34 steps per Lead session are workflow commands (1.15 Tickets per run) | **High** (cost) | Designer: `lead-workflow-efficiency-design-v0.1.md` (F15) |
| L2 | `harness wait` waits on one run at a time, in short slices through the Lead's shell | Medium | Post-M3 (M4) |
| X1 | Refusals say what is wrong but not what to do instead (`evidence ingest` on a mutating Ticket) | Medium | Before review |
| X2 | `resume`'s next actions name commands without their syntax: 37 `--help` lookups in 29 Lead sessions | Low | Before review |
| X3 | The headless Lead's read-only `git` allow-list is too narrow (O2) | Low | Post-M3 |
| X4 | Leads never used the Class 0 path after the hardening | Low | Designer |
| D1 | `README.md` still says "milestone M1" | Medium (first thing a reviewer reads) | Before review |
| D2 | The testing strategy's cost section describes pure-Python YAML, replaced in step 7 | Low | Before review |
| D3 | `m3-dogfood-report.md` §6.3 overstates waiting as the Lead's cost driver (corrected by L1) | Low | Before review |
| T1 | No coverage measurement (already an open decision in the testing strategy) | Medium | Post-M3 |
| T2 | Load-sensitive timing: a launch acknowledgement timeout seen once under two concurrent suites | Low | Post-M3 |
| T3 | The dogfood's command log records the harness tool's status, not `aew`'s exit code | Low | Post-M3 (next dogfood) |
| T4 | The live lane has no scheduled run, so OpenCode drift within V2 is caught only at launch | Low | Designer or operator |
| A1 | The Engine is one class assembled from 13 mixins that call each other implicitly | Low | Post-M3 |
| A2 | `aew doctor` does not report whether YAML uses libyaml; the step-7 speed-up depends on it | Low | Before review |
| A3 | A run's bridge serves one request at a time, so a long `check.run` blocks the run's `whoami` and `submit` | Low | Post-M3 |
| A4 | Known, already tracked: linear control-state cost (ADR-0011) and its false `lost` heartbeats at 3,000 units | — | Tracked (F1) |

**Status (2026-09-29), after the operator's and designer's dispositions:**
- **Done before the review:**
  - C1: the branch is pushed and CI runs on PR #5;
  - X1, X2: refusals and next actions name the command that applies (`d2f8972`);
  - A2: `aew doctor` reports the YAML backend (`c7be45b`);
  - D1, D2, D3: the README, the testing strategy and a dated correction in the dogfood report.
- **Next:** C2, re-sizing shards after a complete CI run; X4, targeted Class 0 runs of T1, which record classification calibration as an explicit issue; T3, instrumenting the dogfood's command log first.
- **Tracked:** L1 as F15 (the Lead workflow efficiency design); X3 as O2; L2, T1, T2, T4, A1, A3 and the lint cleanup as E1 to E7 in `future-work.md` §6.
- The designer's independent audit (I1 to I5) and its fixes: `review-response-2026-09-29.md`.

## 1. CI and CD

### C1. CI has never run on M3 (High, before review)

`impl/m3-opencode` exists only locally: it is 31 commits ahead of `origin/main`, and `origin` has no M3 branch. So the `assurance` merge gate, which requires every collected test to run exactly once and pass on both Linux (Python 3.11) and Windows (Python 3.13), has never run on M3.

Every M3 result so far is local: Windows on the operator's machine, and Linux under WSL through an rsync'd copy. Those are the same two platforms and Python versions, but not CI's machines, clean checkouts, sharding or `check_assurance.py`. M2's review had green CI behind it.

**Recommendation:** push the branch and open a draft PR (the operator's decision, since it publishes the branch), so that `assurance` runs before the independent review. Expect C2 to show up there.

### C2. Shard sizing predates M3 (Medium, with C1)

`tests/durations.json` was last refreshed on 2026-09-26 for M2 (`9553cb7`). It holds 651 Linux and 646 Windows entries, **none of them M3 tests**. M3 added about 300 tests, many of them among the slowest (real supervisor processes, fake V2 servers, Lead sessions). The shard counts in `ci.yml` came from the M2 timings, and each lane job has a 30-minute timeout.

The nightly `reference` job refreshes the timings, but only for `main`.

**Recommendation:** after C1's first run, refresh `tests/durations.json` from that run's lane reports (`tools/ci/update_durations.py`) and re-size the shards if any lane is near its timeout. The local timings in §3 give a first estimate.

## 2. The Lead's cost

The dogfood report put the Lead at about 40% of AEW's cost (Luna 43%, Sol 41%), and blamed much of it on `harness wait` re-sending the whole context (§6.3, O4). Re-analysing the 29 Lead sessions of the 26 hardened AEW runs **corrects that**.

| Lead step kind | Median per session | Total (29 sessions) |
|---|---|---|
| Workflow commands (`work`, `plan`, `invoke`, `review`, `verify`, `integrate`, `evidence`) | 20 | 553 |
| Reads (`status`, `resume`, `work show`, `harness status`, …) | 6 | 168 |
| `harness wait` | 4 | 117 |
| File tools (read, glob, grep) | 1 | 92 |
| `git` | 1 | 50 |
| `authority` (project setup) | 2 | 48 |
| `--help` | 1 | 37 |
| **All steps** | **34** | 977 |

A run had 1.15 Tickets on average. The median Lead session read 261,000 cached tokens: every step re-reads the conversation so far.

### L1. Step count drives the Lead's cost (High for cost; designer)

Waiting is 12% of the Lead's steps, though it is about 55% of its wall time (median 90 s of 163 s). The cost is the **choreography**: taking one Class 1 Ticket from creation to DONE is about 20 separate Lead commands, each a model step that re-reads a growing context. In order:
- create;
- plan propose, plan accept;
- assign with `--launch`, wait;
- transition to REVIEW_PENDING, invoke the reviewer with `--launch`, wait, ingest the review;
- transition to VERIFY_PENDING, invoke the verifier with `--launch`, wait, ingest the verification;
- transition to COMMIT_READY, integrate prepare, invoke the post-integration verifier, wait, ingest it;
- publish.

Each command also takes `--expect-rev`, which is why Leads read status between steps.

This is a property of the Lead's interface, not a defect. Every step is a real decision point in the Workflow Contract. The options are for the designer:
- **Compound Lead operations** that perform a fixed, gate-checked sequence in one call. For example, "transition to REVIEW_PENDING and dispatch the planned reviewer with `--launch`" as one command, or `aew work advance <T>`, which takes the single next step the engine already computes for `resume`'s next actions. Each step would still be recorded and gate-checked separately.
- **Returning the next action and the new revision** from every mutation, so the Lead never needs a read in between. Mutations already return the revision; `resume` already computes next actions.
- **A cheaper Lead model for routine steps**, which is routing (ADR-0010) and conflicts with the plan assurance design's strong-Lead recommendation (F14 §23). This needs the designer's judgement.

The first option would cut the Lead's steps per Ticket roughly in half without removing any gate. It interacts with F14, which adds steps before dispatch.

### L2. `harness wait` (Medium, post-M3)

`harness_wait` polls one run's record every 0.2 s until it stops or times out (`harness_ops.py:324`). The Lead calls it through its harness shell. The dogfood brief told Leads to wait in 110-second slices, to stay within the shell tool's command timeout; OpenCode's exact default was not verified for this audit. Two consequences:
- each slice is a model step (4 per session here; more with longer runs);
- it waits on one named run. With concurrency above 1 (M4), a Lead would need to wait on any of several runs.

**Recommendation (M4):** a `wait-any` over the Lead's live runs, and a push-style wake from the supervisor, as the coordination design's event delivery (F9) already anticipates. Low value before M4, since waits are a small part of cost (L1).

## 3. Testing

**Local suite run for this audit** (Windows, Python 3.13, `-n auto`, not the serial lane, at `e6ab7cb`):
- **951 passed, 4 skipped** (the pinned platform skips), in 670 s (step 7 measured 610 s).
- The isolation guard then reported one change to the checkout: this report, written while the run was in progress. Nothing a test wrote.
- **The slowest tests are M1 and M2 scenarios, not M3's.** They are led by AT-13's backlog scenario (168 s), an M2 composition (118 s) and the Story lifecycle (93 s). They are CLI-subprocess heavy, as the testing strategy's §12 describes.
- **M3's slowest** are the AT-14..AT-17 scenarios (31–55 s each, in two drivers), the pack-pinning regression for M3-D1 (73 s) and the scale regression (49 s). Seven of the 60 slowest tests are harness acceptance scenarios, so the acceptance lane is where C2's re-sizing matters most.
- A single test takes 168 s, which bounds how far sharding can shorten a lane.

### T1. No coverage measurement (Medium, post-M3)

No coverage tool is installed or configured. The testing strategy already records "the ruleset's code-coverage rule has no report yet; subprocess-aware coverage, combined across shards, is a separate decision". For M3 this matters more than before: most harness code runs in subprocesses (supervisor, bridge, broker, fake servers), which only subprocess-aware coverage sees.

**Recommendation:** one measured run with `coverage` in subprocess mode (`COVERAGE_PROCESS_START`) over the harness packages, to find unexercised error paths in `supervisor.py`, `bridge.py`, `lead_broker.py` and `adapter.py`. It needs no CI change to learn from.

### T2. Load-sensitive timing (Low, post-M3)

Step 9 saw one Windows failure: a launch acknowledgement timed out while the Linux suite ran concurrently on the same machine. It passed on rerun, and the suites now run one after the other. `AEW_LAUNCH_ACK_S` defaults to 90 s. The step-3 report records a similar single failure under about 40-way overload (`test_an_acquired_seat_is_released_or_held_explicitly`).

Neither has reproduced under normal load. **Recommendation:** watch C1's first CI runs, whose runners are slower than the operator's machine. If either recurs, raise the test-side timeouts, not the product's.

**Update (PR #5 CI):** the second one was not a timeout. It recurred on CI's Linux runner, and it was a real race in the Lead broker, M3-D11: a session ending while the broker's watchdog was mid-check was reported "superseded". It is fixed, with a deterministic regression (ADR-0009). CI also exposed a race in the fake OpenCode server (it reported a turn idle before saving it); that was a test-helper fix.

### T3. The dogfood's command log (Low, next dogfood)

`headless.command_log` records each shell call's harness status (`completed` or `error`) but not `aew`'s exit code. A refused `aew` command (wrong state, wrong key, a `USAGE` error) shows as `completed`. The dogfood report's friction counts (§6.3) were therefore gathered by reading transcripts.

**Recommendation:** record the exit code and the AEW error code from the shell output, so the next dogfood (Q7, F14 §29) can measure refusals and recovery directly.

### T4. No scheduled live run (Low, designer or operator)

The live lane is opt-in and manual, by design (a real binary, a model, the operator's machine). OpenCode V2 has no stability policy and the Desktop app auto-updates its own copy. AEW pins the versioned 2.0.18 CLI and probes capabilities at every launch, so drift fails closed rather than silently. But nothing notices a new version until someone upgrades.

**Recommendation:** decide whether a periodic live smoke run on the operator's machine is worth it (free models, the conformance scenarios only). It is optional.

## 4. Friction exposed by live and dogfood runs

### X1. Refusals that do not say what to do instead (Medium, before review)

Most Leads made one to three calls that an error message then corrected (dogfood report §6.3). The most common was `aew evidence ingest` on an implementation report. The refusal says "`aew evidence ingest` applies to non-mutating (evidence-only) Tickets; T-0001 is a mutating Ticket" (`nonmutating_ops.py:65`), but not that a mutating Ticket's report is accepted by the RUNNING → REVIEW_PENDING transition.

Wrong-state refusals (`work assign`, `dispatch`) are similar: they name the state, not the command that applies in it.

**Recommendation:** add the applicable next command to these refusals, as M3-D9 did for the comma in a scope glob. This is a message-only change, with a regression each. It saves a model step per occurrence.

### X2. Next actions without syntax (Low, before review)

`aew resume` lists "classify authority candidates: `aew authority list`, then accept/reject". Leads then ran `aew authority --help` 20 times across 29 sessions, and `--help` 37 times in all. Every dogfood run was a fresh project, so project setup happened every time, which overstates this for real use.

**Recommendation:** next actions give a runnable template, for example `aew authority accept C-001 --class <decisions|…> --expect-rev N`.

### X3. The headless Lead's `git` allow-list (Low, post-M3)

Already O2. `git ls-files` was rejected 11 times, plus `git ls-tree`, `git -C`, chained commands and `git branch`. The TUI asks the operator; a headless Lead cannot ask. It matters when a Lead runs headless (F8, the next dogfood).

### X4. The Class 0 path went unused (Low, designer)

After the hardening, Leads chose Class 1 or 2 for every task, T1 included, so the Class 0 fast path (local checks only) never ran. This is consistent with fail-closed classification (F6) and with F14's "simple is not safe". It is a policy question, not a defect.

## 5. Documentation drift

- **D1.** `README.md`'s status section still describes "milestone M1, the first serial vertical slice". It predates M2's merge. **Before review:** point it to M3 and to `implementation-status.md`.
- **D2.** `testing-and-ci-strategy.md` §12 says a read-only call spends "~65 ms of pure-Python YAML parsing". Step 7 moved YAML to libyaml. **Before review:** update from `m3-performance.md`.
- **D3.** `m3-dogfood-report.md` §6.3 and `future-work.md` O4 present waiting as a large part of the Lead's cost. L1 above shows it is 12% of steps. **Before review:** add a correction note that points here, without rewriting the report's pre-registered results.

## 6. Architecture

### A1. The Engine is one class from 13 mixins (Low, post-M3)

`Engine` combines 13 `*Ops` mixins over `EngineBase` (15 classes in its method resolution order, 246 attributes). Mixins call each other's methods and hooks implicitly: 7 `type: ignore[attr-defined]` markers, and hooks such as `_before_state_change` and `_after_state_change` that later mixins refine. It works and is well tested. But which override wins depends on the order of the base classes, and the two largest mixins are 865 and 827 lines (`nonmutating_ops.py`, `evidence_ops.py`).

**Recommendation:** no change before the review. When ADR-0011 restructures state access before M4, consider explicit collaborators for the hook points (state-change effects, gate evaluation) instead of MRO-dependent overrides.

### A2. The YAML backend is invisible (Low, before review)

The step-7 speed-up (3.8–5.9×) relies on PyYAML being built with libyaml. It is on Windows and in the WSL venv. It is not known for the offline Rocky 8 wheelhouse (SPT `core-python.lock`), and AEW falls back to pure Python silently.

**Recommendation:** `aew doctor` reports the YAML backend, WARN when pure Python. The operator can then check the target once.

### A3. The bridge is serialized per run (Low, post-M3)

`BridgeServer` handles one request at a time per run (`bridge.py`, the `_serial` lock). A `check.run` that runs a long test suite therefore blocks that run's `whoami` and `submit` until it finishes. This is correct: the requests are the same agent's, and the lock keeps the authority re-check and the engine call together. It becomes visible with long checks, or if a harness runs tools in parallel.

**Recommendation:** keep it for now. If needed, serialize only mutating operations and let `whoami` through.

### A4. Already tracked

- Control-state cost grows linearly with history (ADR-0011, F1): an M4 prerequisite.
- At 3,000 units, a supervisor's re-parse after each Lead commit takes longer than the 10 s staleness limit, so a healthy run can briefly show as `lost` (`m3-performance.md` §5). ADR-0011 resolves both.

## 7. Not found

Checked, with no issue found:
- **Error paths through the bridge are redacted.** `BRIDGE_ERROR` includes exception text, but every reply, errors included, goes through `redact()` before it is sent (`bridge.py:163`).
- **The M1 and M2 reviewer probes and acceptance files are unchanged** since `adef640`.
- **CLI startup** is about 0.1 s (`aew --version`), with the M3 imports included; not a cost driver.
- **The nightly lane** already covers the other Python and OS combinations (`matrix-extra`), so CI's two-combination matrix is not a gap.
