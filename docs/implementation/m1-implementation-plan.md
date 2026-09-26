# AEW — Implementation Plan for the First Serial Vertical Slice (M1)

## Context

AEW (Agent Engineering Workflow) is specified by a frozen set pinned by `docs/aew-spec-manifest-v0.2.yaml`: Workflow Contract v0.7 (**WC**), Knowledge Contract v0.4 (**KC**), embedded Capability Contract (WC §16), and the SPT remediation appendix v0.2 (**SPT-R**, a bootstrap backlog, not a workflow authority). Nothing is implemented yet. The AEW repo (`Agentic-Engineering-Workflow`) has 2 commits and the spec docs are **untracked**. WC §21.2 steps 3–5 and KC §25–26 define the first deliverable: a deterministic state engine proving one complete **serial** Ticket lifecycle plus three adversarial cases (unintegrated dependency, stale evidence, crash/superseded Lead). This plan builds that slice without redesigning the frozen architecture. Where the spec is silent, the gap is flagged (§8) instead of filled in silently.

**Plan review (2026-09-25):** approved to begin **Step 0** once review corrections §1–§5 and wording fixes A–B are in. They are now incorporated:
- §1: operator authorization for takeover (§4.2).
- §2: atomic ref CAS for publication (§4.7).
- §3: token verifiers (§4.2).
- §4: `init` records candidates only (Step 10).
- §5: evaluate the internal explorer (D-op-1, §9 A5).
- A: §7 renamed to target status at M1 completion.
- B: AT-1 uses an operator-authorized takeover.

There will be no further general architecture review. Escalate only on a frozen-contract contradiction, a missing authority boundary, an unsafe state transition, or an invariant the implementation cannot satisfy. Libraries, IDs, paths, schemas, locking primitives, git plumbing and module layout remain implementation decisions.

**Verdict: no architecture blockers for AEW M1.** The two semantic gaps are now **resolved by operator decision (2026-09-25)**:
- **A1:** integration validates before it publishes.
- **A2:** Lead takeover must be operator-confirmed.

The remaining SPT-side blocker is an input: the audited Ghidra bridge environment. It does not block AEW M1.

**Operator decisions recorded (2026-09-25).** These become AEW Decision records once the engine exists.
- **D-op-1:** The SPT target repo is `security-platform-toolchain`. **Correction (plan review):** the lightweight Python repository explorer *does* exist. An internal LLM built it internally as a pragmatic GitNexus replacement, and it was never committed to the external SPT repo. Plan: evaluate that internal explorer, then adopt it as-is, generalize/port it, or replace it if it is unsuitable or unavailable (§9 A5). Until then, `repository_exploration` has three providers:
  - Git CLI: the guaranteed fallback.
  - The internal Python explorer: a candidate provider.
  - GitNexus: the richer relationship/impact provider.

  The explorer is never called "GitNexus Lite", and GitNexus relationship semantics are never claimed for it.
- **D-op-2:** Integration order is **validate, then publish** (§4.7). Publication is an **atomic git ref compare-and-swap** (plan review §2).
- **D-op-3:** Lead takeover requires **real out-of-band operator authorization**, as in plan review §1. A flag, boolean or reason is **not** authorization. M1 uses interactive confirmation on the controlling terminal (§4.2). "Any Lead with a reason" is rejected as too weak. Automatic takeover is **Designed** for the future: an operator-issued one-time token, an approval artifact, or a formally defined Lead lease that has expired, after which the engine atomically grants the successor an exclusive new authority epoch (epoch = generation).
- **D-op-4:** **OpenCode** is the first harness/CLI adapter target (M3). You offered to install OpenCode locally for verification. It isn't needed for M1; please install it before M3, preferably in WSL to mirror Rocky Linux.

---

## 0. Inspection findings (facts that shape the plan)

| Finding | Consequence |
|---|---|
| AEW repo: `main` @ `686768b`; `docs/` untracked | Step 0 pins the frozen set (commit + tag + hash record) before any code. |
| Local SPT repo is **`security-platform-toolchain`** (confirmed as the SPT target, D-op-1). Branch `python-whl-1.2` has ~20 modified and several untracked files (WIP). | No SPT edits until the WIP is committed or stashed. M1 does not touch SPT. |
| SPT has `images/gitnexus` (GitNexus 1.6.3, stdio MCP, offline Ladybug patch), `images/ghidra-mcp` (bethington v5.5.0 `bridge`/`headless`), `ghidra-base` 12.0.4, `ghidra-exporter`, and `scripts/doctor.sh` (OK/WARN/FAIL). | These are reused as-is where possible (§9). |
| **No Python repository explorer exists in SPT, including its git history.** No OpenCode or MCP client config and no capability manifests exist either. | SPT-R §2.3 and P1-8 cannot be done from this repo. See the blocker in §8 (C1). |
| GitNexus runs as a hard-coded `spt` user (1001:1001). `HOME=/tmp/spt-home` is ephemeral. The index is written to `<target>/.gitnexus`, owned by uid 1001. | This confirms the SPT-R §2.1/§2.2 defects. |
| Ghidra takes local paths only (`GHIDRA_TARGET`) and uses a `/tmp` project with `-deleteProject`. `GHIDRA_MCP_AUTH_TOKEN`, `GHIDRA_MCP_FILE_ROOT` and `GHIDRA_MCP_ALLOW_SCRIPTS` are documented in the README but not wired up. | This confirms SPT-R §4. The env vars must come from the audited environment and must not be invented (SPT-R §4.2). |
| Additional SPT defects found during inspection: `GITNEXUS_FIXTURE_REPO=1` runs `rm -rf $GITNEXUS_TARGET`, which defaults to `/workspace`; stale `clone`/`upload` callers; the Makefile references empty `examples/gitnexus-*-smoke/` directories; root-running images fail `container-structure-test`. | These become **new Tickets with "discovered" provenance** at import. They are not silently added to the frozen backlog. |
| SPT's py311 wheelhouse already pins `pyyaml==6.0.3`, `jsonschema==4.26.0` and `pytest==9.0.3` (Rocky 8 / glibc 2.28). | AEW runtime deps = PyYAML + jsonschema, so an offline Rocky 8 install needs no new wheels. |
| Dev host is Windows 11 with Python 3.13 and Git 2.46. WSL Ubuntu 22.04 has python3.11 and Docker 29.8. OpenCode, Rocky 8 and GPT-5.4 are not available here. | Tests run on both Windows and Linux. Linux crash/lock tests must run on WSL-native ext4, not `/mnt/c` (drvfs rename/flock semantics differ). The M1 core is harness-neutral. |

---

## 1. Architecture and authority boundaries (my understanding)

AEW is **not** a model runtime or harness (WC §3). It is a deterministic **state engine + knowledge store + role/launch-contract generator**. Harnesses (OpenCode first, others later) run the LLM contexts. Those contexts drive AEW through one CLI, and later an MCP adapter, over **one engine API** (WC §15.6, invariant 21).

- **Project Control Plane:** the Lead owns objective, classification, plan acceptance, dispatch, failure classification, integration and completion (WC §5.1, §6).
- **Engineering Execution Plane:** bounded role invocations (Implementer, Reviewer, Verifier, ...). They are created by the Lead, receive assembled context packs, and write back **evidence only** (KC §7.3, §16).

Authority as it will be **enforced** by the engine (not just documented):

| Concern (WC §6 / KC §16) | Writer | Enforcement mechanism |
|---|---|---|
| Control state: work states, classification, accepted-plan pointer, dependencies, workspace/integration disposition, waivers, completion | Current Lead only | A Lead token carrying its authority **generation**, plus an `--expect-rev` CAS on the control revision, applied inside an exclusive critical section. Stale generation → `STALE_AUTHORITY`; stale revision → `STALE_REVISION`. |
| Lead authority transfer | Current Lead (cooperative handoff), or an operator-confirmed takeover (§8 A2) | Generation increments atomically, and every older token is dead from then on. |
| Implementation report / review report / verification record | Implementer / Reviewer / Verifier invocation | An invocation token scoped to (role, work unit). Evidence is immutable, create-if-absent, and cannot carry control fields. |
| Verification-failure classification | Lead only | A separate decision record. A Verifier cannot submit it. The state mapping is fixed (WC §8). |
| Ticket state after review/verify | Engine, on Lead ingest | Determined **mechanically** by the role's recorded result. The Lead cannot turn FAIL into VERIFIED (§8 B1). |
| Evidence identity | Engine | The engine computes the evaluated snapshot itself: the check runner fingerprints before and after, and invocations are bound to the snapshot their pack was built from. It never takes the agent's claim. |
| Derived knowledge, context packs, rendered views, locks, tmp | Rebuildable | Stored under `.aew/local/` (ignored) or rendered from control state. Deleting them never loses authority (KC §5.3, §21). |
| Workspace copies of `.aew/` | Nobody | The engine refuses to treat a linked-worktree `.aew/` as an authority (WC §5, KC §12.3). |

Tokens are a **protocol guard against accidental cross-role writes and stale writers**, not an OS security boundary: all roles run as the same UID. This limitation will be documented.

### Normative requirements vs implementation choices

| Normative (spec-fixed) | Implementation choice (this plan's pick) |
|---|---|
| Atomic, version-aware control updates; stale Lead rejected; crash → previous or new state (WC §5, §8.2; KC §12.3) | Single `control.yaml` as commit point; OS advisory lock; temp+fsync+`os.replace`; post-commit log/render with repair |
| Evidence bound to evaluated snapshot incl. uncommitted inputs; AEW files excluded (WC §9.9; KC §11) | Git temp-index `write-tree` over tracked + untracked-non-ignored files, with `.aew/` removed |
| Mutating dep satisfied only by integrated + post-integration-validated output present in the downstream snapshot (WC §8, §8.1; KC §9.5) | Dependency = upstream DONE **and** `git merge-base --is-ancestor <integrated> <assignment base>` |
| Mutating concurrency = 1 without isolation (WC §8.1, §21.1; KC §25) | Strict serial: at most one mutating Ticket holding a live unintegrated workspace |
| Controlled, attributable, serialized integration + revalidation (WC §8.1, §13) | Git worktree per mutating Ticket; Lead-driven integration saga (§4.7) |
| Human-readable + machine-queryable durable state (KC §27.3–4) | Markdown with YAML frontmatter for records; YAML for control/policy; `--json` on every query |
| Knowledge classes, logical names, resolver (KC §8, §14) | `.aew/` layout (§3); hard-bound resolver from logical names to manifest keys |
| Guardrails representable and enforceable where practical (WC §16.15; KC §8.11) | `policy/guardrails.yaml` with deterministic rules (protected/generated paths, Ticket scope, review triggers) |
| Role definitions stored as durable workflow artifacts (WC §5) | Packaged `roles/*.yaml` |
| IDs, file split, frontmatter vs YAML, lock mechanism (KC §28) | `T-0001`/`S-0001`/`E-0001`, `INV-0001`, `D-0001`; evidence IDs scoped to invocations |

---

## 2. Proposed AEW repository structure

```text
Agentic-Engineering-Workflow/
  pyproject.toml                # PEP 621; requires-python >=3.11; deps: PyYAML, jsonschema; console script `aew`
  docs/                         # frozen spec set (unchanged) + spec-pin.yaml (sha256 of each)
  docs/implementation/
    adr/                        # ADR-0001 persistence, -0002 snapshot, -0003 transition table, -0004 integration, ...
    ambiguity-report.md         # §8 of this plan, with dispositions
    implementation-status.md    # WC Appendix C table: Implemented / Staged / Designed
  src/aew/
    cli/                        # argparse adapter ONLY (no logic): main.py + commands/*.py
    engine/
      api.py                    # Engine facade: the single authority used by CLI (and a future MCP adapter)
      store.py                  # lock, CAS, atomic replace, recovery, post-commit log/render, fault-injection points
      control.py                # control-state model (revision, lead{generation}, work, invocations, integration)
      authority.py              # Lead acquire/handoff/takeover; invocation tokens; role-permission matrix
      transitions.py            # Ticket state machine table + guards; BLOCKED/READY recompute
      gates.py                  # effective obligations (local class path + inherited gates + floor + triggers); CURRENT/STALE/MISSING
      dependencies.py           # mutating vs evidence-only satisfaction; ancestry check
    knowledge/
      manifest.py               # project.yaml; logical-name resolver
      records.py                # Epic/Story/Ticket, plan revisions, decisions (md + frontmatter)
      evidence.py               # immutable evidence records + provenance (what/who/when/against/how/result/evidence)
      context.py                # packs: lead-resume, implementer, reviewer, verifier; launch contracts (WC §15.4)
      render.py                 # CURRENT.md, HANDOFF.md, /status projections
    snapshot/fingerprint.py     # evaluated snapshot identity
    workspace/
      git.py                    # thin subprocess wrapper
      worktrees.py              # allocate/inspect/release; authority resolution from inside a worktree
      integration.py            # prepare → post-integration verify → publish (CAS) → reconcile
    policy/
      guardrails.py             # deterministic guardrail checks against the Ticket diff
      checks.py                 # project-defined check runner → check evidence
    roles/*.yaml                # lead, implementer, reviewer, verifier, planner, investigator definitions
    schemas/*.json              # manifest, control, work-unit, plan, evidence kinds, guardrails, gates, role
    templates/init/             # .aew skeleton for `aew init`
  tests/
    unit/  integration/  acceptance/
    harness/roles.py            # scripted deterministic Implementer/Reviewer/Verifier drivers (CLI subprocesses)
    fixtures/sample_project/    # tiny Python package + tests used by the acceptance scenarios
  .github/workflows/ci.yml      # pytest matrix: ubuntu/py3.11 + windows/py3.13
```

M1 has no `providers/` module. The Capability Contract is not load-bearing for the slice (WC §16), and the only provider in use is the project-defined check runner.

## 3. Per-project knowledge layout (`.aew/`, an implementation choice under KC §22)

```text
.aew/
  project.yaml                 # manifest: identity, repository{authoritative_branch}, authority refs, knowledge map, control_state, records, policy
  knowledge/PROJECT.md  OPEN-QUESTIONS.md  [CODEBASE.md w/ source_revision]
  policy/guardrails.yaml  checks.yaml  gates.yaml     # guardrails; build/test commands + baseline failures; risk-class gate paths, post-integration policy, mutating_concurrency: 1
  state/control.yaml           # AUTHORITATIVE mutable control state (the single atomic commit point)
  state/CURRENT.md             # rendered projection, stamped with revision ("generated — do not edit")
  state/HANDOFF.md             # latest handoff/checkpoint (written via engine transition)
  state/log/000042.yaml        # immutable transition history (actor, generation, op, reason, refs, before→after)
  work/T-0001/ticket.md  plan-v1.md      # records; accepted plans immutable (sha256 pinned in control.yaml)
  evidence/T-0001/INV-0003-impl.md  INV-0004-review.md  INV-0005-verify.md  CHK-*.yaml  logs/
  decisions/D-0001.md          # classifications, waivers, authority transfers, promotions
  local/                       # gitignored: lock, tmp, context packs, caches
```

Ticket workspaces default to `<repo-parent>/.aew-workspaces/<project-id>/T-0001` (configurable). Each workspace carries a per-worktree marker stored in its **git dir**, so the marker is never part of the fingerprint.

---

## 4. Core mechanisms

**4.1 Control-state persistence (WC §5, §8.2; KC §12.3).** Every mutation runs one sequence:
1. Acquire an OS advisory lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows). The OS releases it when the process dies.
2. Run recovery: delete stale temp files; verify `control.yaml` parses and its embedded checksum matches; repair a missing log entry or a stale render from `last_transition`.
3. Check the generation and `--expect-rev`, then check state-machine legality.
4. Write any new immutable files first. They stay unreferenced, and therefore harmless, until commit.
5. Write `control.yaml.tmp`, fsync it, `os.replace` it (**the commit point**), then fsync the directory on POSIX.
6. After commit, append to the log and re-render CURRENT.md.

A crash at any point leaves revision N or N+1, never a hybrid. Named fault points are hit via `AEW_FAULT=<point>`, which calls `os._exit` for real process death. On Windows, a failed replace is retried with bounded backoff while another process holds the target open. A corrupt `control.yaml` (external damage) makes the engine fail closed, and `doctor` reports it.

**4.2 Lead authority.**
- `lead acquire`: only when the Lead seat is vacant (first acquisition after `init`, or after a clean release).
- `lead handoff offer`: A writes the handoff and gets a one-time offer secret. The seat becomes `handoff_pending`, and A can then only cancel.
- `lead handoff accept --offer <secret>`: B, after `aew resume`. Generation becomes g+1. Invocations listed in the handoff carry forward; everything else is revoked.
- `lead takeover --reason "..."`: **operator-authorized**. Generation becomes g+1. All prior Lead tokens and all in-flight invocation tokens are revoked. In-flight Tickets become `INTERRUPTED`. A Decision record is written with the reason, the old and new holders, and `authorized_by: operator-tty`.

**Operator authorization for takeover (D-op-3).**
- The engine gets confirmation itself, inside the takeover operation. It reads from the controlling terminal: `/dev/tty` on POSIX, `CONIN$` on Windows. It never reads from argv, environment variables, stdin, or an API argument.
- The engine displays a one-time challenge (project id + new generation + random code), and the operator must type it back.
- With no controlling terminal, which is the normal case for a harness tool call, the takeover is rejected with `OPERATOR_AUTHORIZATION_REQUIRED`.
- There is no flag or env var that bypasses this.
- Documented residual risk (acceptable for M1 per review): a same-UID agent that deliberately fakes a pseudo-terminal or patches the process is outside the M1 threat model. The future designs above (an operator token held outside the agent's reach, an approval artifact, or lease expiry) close that gap.
- The `lead` record is schema-versioned, so those designs can be added through an ADR without migrating state.

**Token verification across processes (plan review §3).** Every mutating CLI call is a separate process, so tokens are verified against durable **verifiers**. The raw secret is never stored durably.
- **Format:** `aew1.<token_id>.<secret>`, where the secret is 256-bit random and urlsafe. It is printed once on stdout to the caller: the Lead for its own token and for each invocation token it issues. The Lead passes invocation tokens to subagents in the spawn prompt. Launch-contract and context-pack files on disk carry a placeholder, never the token.
- **Durable (in `control.yaml`):** `token_id → {sha256(secret), kind: lead|invocation, scope, issued_at, issued_by_generation, expires_at?, revoked_at?, revoke_reason?}`.
  - Lead scope: `{session_id, generation}`.
  - Invocation scope: `{invocation_id, role, work_unit, generation}`.
- **Verification:** look up `token_id`, then `hmac.compare_digest(sha256(secret), verifier)`. Then check scope: the role, work unit and permitted operation must match the request. The token must not be revoked or expired.
  - A Lead token is valid only while its generation equals the current generation.
  - An invocation token is valid only while its invocation is `active` and its generation is current (or carried forward by a handoff).
- **Revocation** (atomic, inside the same control transition): on invocation completion or cancellation, on takeover (all tokens), and on handoff accept (anything not carried forward).

`aew resume` is read-only and needs no token.

**4.3 Ticket state machine (WC §8; table recorded in ADR-0003).** WC calls this a "typical" state model. Unlisted transitions below are conservative choices, and every regression is Lead-initiated with a reason.

| From → To | Guard |
|---|---|
| BLOCKED ⇄ READY | Recomputed by the engine inside every committed transition: plan/assignment accepted ∧ deps satisfied ∧ not cancelled |
| READY → ASSIGNED | Lead. Serial cap free. Workspace allocated from the authoritative HEAD. **Base snapshot recorded.** Each mutating dep's integrated commit must be an ancestor of that base. An implementer invocation is created. |
| ASSIGNED → RUNNING | Lead (dispatch confirmed) |
| RUNNING → REVIEW_PENDING | An implementation report from the assigned invocation exists, and the required local checks pass and are **CURRENT** on the current snapshot |
| REVIEW_PENDING → REVIEW_PASSED/FAILED | Review ingest. The reviewer invocation ≠ the implementer invocation, independence is at least R1, and the result follows the report's disposition. Open Blocker/Major findings mean FAILED unless waived by policy. |
| REVIEW_FAILED → RUNNING | Findings recorded (WC §8) |
| REVIEW_PASSED → VERIFY_PENDING | Review gate CURRENT; verifier invocation created |
| VERIFY_PENDING → VERIFIED / VERIFICATION_FAILED / VERIFICATION_INCONCLUSIVE | Mechanical from the verifier result. Pass requires both a goal-backwards claim and a contract claim. `blocked` maps to INCONCLUSIVE (§8 B2). |
| VERIFICATION_FAILED → RUNNING / REPLAN_REQUIRED / VERIFICATION_INCONCLUSIVE | Lead classification only: LOCAL_IMPLEMENTATION_DEFECT → RUNNING (failure evidence attached); PLAN_OR_DESIGN_DEFECT or CONTRACT_VIOLATION → REPLAN_REQUIRED; ENVIRONMENT_OR_EVIDENCE_BLOCKED → INCONCLUSIVE |
| VERIFICATION_INCONCLUSIVE → VERIFY_PENDING | Lead, with a reason |
| VERIFIED → COMMIT_READY | All effective gates CURRENT on the current snapshot; mandatory findings resolved or waived by policy |
| COMMIT_READY → DONE | Only via the integration saga (4.7) |
| {REVIEW_*, VERIFY_*, VERIFIED, COMMIT_READY} → RUNNING | Lead, with a reason (e.g. evidence stale or further mutation needed) |
| any active → INTERRUPTED; INTERRUPTED → prior phase | Takeover, or Lead reconcile with a workspace-inspection record. **Success is never inferred.** |
| any non-terminal → REPLAN_REQUIRED / ESCALATED / CANCELLED | Lead, with a reason. REPLAN_REQUIRED → BLOCKED/READY once a new plan revision is accepted. |

**4.4 Evaluated snapshot (WC §9.9; KC §11).** A snapshot is `{base_revision, workspace_id, relevant_inputs_fingerprint, artifact_digests[]}`. The fingerprint is computed as follows:
1. Copy the workspace index to a temp index.
2. `git add -A` to capture tracked plus untracked-non-ignored files.
3. `git rm -r --cached .aew` to drop AEW's own files.
4. Force-add any `policy.fingerprint.include_ignored` paths.
5. `git write-tree`. The fingerprint is `git-tree:<oid>`.

Writing AEW reports never changes it. Changing a source, config, or untracked input always does. Documented limitations: submodule dirty state, LFS content, and changes that only differ in line endings (normalized by git).

**4.5 Gates and staleness.**
- Effective obligations = local risk-class path + inherited non-waivable ancestor gates + any recorded minimum-class floor + triggered review gates (WC §7.4). This is a pure function. M1 exercises Class 0/1; Story inheritance is fully exercised in M2.
- A gate is satisfied only by passing evidence whose snapshot fingerprint equals the **current** workspace fingerprint and whose plan revision equals the accepted one.
- Otherwise the gate is `STALE` or `MISSING`. Evidence files are never modified, and staleness is computed, never written.
- Forward transitions fail closed when a gate is not satisfied.

**4.6 Dependencies.**
- An edge's `kind` is `mutating` or `evidence`. It defaults to mutating when the upstream Ticket is mutating.
- A mutating edge is satisfied only when the upstream Ticket is DONE (integrated and post-integration validated) **and** its integrated commit is an ancestor of the downstream assignment's recorded base.
- An evidence edge is satisfied by accepted durable evidence.

**4.7 Workspace and integration (serial).** Each mutating Ticket gets its own git worktree and branch `aew/T-0001`, even in serial mode. This gives a real integration candidate and keeps unaccepted changes out of other Tickets' snapshots. Integration is a saga, and each step is a recorded control transition:
1. **prepare:** COMMIT_READY and all gates CURRENT. Commit the workspace. The committed tree's fingerprint must equal the gated fingerprint. In an integration worktree, merge the Ticket branch onto the authoritative ref's current commit H. The result is candidate M, recorded as `integration{base: H, candidate: M}`.
2. **post-integration verification:** a Verifier invocation runs the policy's post-integration checks, and the resulting evidence is bound to snapshot(M).
3. **publish.** The atomic compare-and-swap on the ref is the **single publication point**:
   1. A control transition records `integration.status = publishing {H → M}`.
   2. `git update-ref -m "aew: integrate T-0001" refs/heads/<authoritative> M H`. Git takes the ref lock and applies the update only if the ref is still H.
   3. **If the CAS fails, the candidate is stale.** Record `integration.status = stale_candidate`, then rebuild from the new authoritative commit and revalidate from step 1. M is never published.
   4. If the CAS succeeds, the control transition marks **DONE** with `integration{commit: M, evidence}`.
4. **Authoritative worktree sync** (a recoverable follow-up; authority already lives in the ref):
   1. **Before publishing**, check that the authoritative worktree and its index match H for every path in `P = diff(H, M)`. `.aew/` can never be in P because the guardrail blocks it.
   2. **After the CAS**, force exactly the paths in P to M's content: checkout the paths present in M, remove the paths deleted in M, and update the index for those paths only.
   3. Other paths are left alone, including dirty `.aew/` control files.
   4. Re-running the sync is idempotent.
   5. The sync status is tracked as `integration.worktree_sync`.
   6. New Ticket workspaces are always created from the **ref**, never from the authoritative worktree, so a lagging view cannot corrupt snapshots.
5. **reconcile** (after a crash), keyed on the recorded `publishing {H → M}`. It inspects git, never assumes:
   - ref == H: retry the CAS.
   - ref contains M: complete DONE, then the sync.
   - ref is anything else: stale candidate.
   - A path in P that matches neither H nor M: the engine refuses and raises a contradiction for the operator.

This ordering (validate, then publish by CAS) is decision D-op-2. A post-integration failure becomes VERIFICATION_FAILED(scope = integration), which goes to Lead classification, and the authoritative branch is never advanced. A merge conflict produces an integration-failed record, and the Lead then chooses RUNNING (rebase) or REPLAN_REQUIRED. The Ticket branch is kept for provenance, and the worktree is removed.

**4.8 Guardrails.**
- **Implemented in M1:** protected paths (`.aew/**` is always protected), generated-file paths, the Ticket's declared scope paths, and path-based review triggers that add required gates. `aew guardrails check` runs them against the base..workspace diff, including uncommitted and untracked files. The results feed contract verification, and integration hard-blocks on any violation.
- **Representable but not enforced in M1:** dependency-direction/layering rules.

**4.9 Context packs and launch contracts (WC §10.1, §15.4; KC §15).**
- Packs are assembled only from durable artifacts, through logical knowledge names.
- **Reviewer pack:** requirement, contracts/guardrails, accepted plan, diff at snapshot S, check outputs, review scope. It excludes implementer rationale. Only the structured "files changed / checks run / declared deviations" fields of the implementation report are included.
- **Verifier pack:** acceptance criteria, expected observable state, and the implementation revision. Implementer claims are labelled as claims.
- Packs are deterministic. The pack manifest (resolved refs + sha256) is recorded on the invocation for provenance.

**4.10 Resume (KC §15.1).** `aew resume --json` outputs, in order:
1. manifest
2. control state
3. active work brief
4. accepted plan/assignment
5. latest handoff
6. open review findings
7. verification failures/blockers
8. guardrails/authority refs
9. derived knowledge with freshness
10. computed next actions + the Lead's `next_action` note
11. **contradictions**: hash mismatch on accepted artifacts, stale render, missing workspace, orphan or active invocations

---

## 5. Ordered implementation plan (M1)

Each step lists spec refs, what it delivers, and its completion criteria and tests. Every step's tests run on both Windows and WSL-native Linux.

| # | Step | Spec refs | Completion criteria / tests |
|---|---|---|---|
| 0 | **Pin frozen spec set.** Branch `impl/m1-serial-slice`. Commit `docs/` unchanged, tag `aew-spec-frozen-2026-09-25`, and add `docs/spec-pin.yaml` (sha256 per doc). Add `docs/implementation/{ambiguity-report.md, implementation-status.md}`. | Manifest freeze_rule; WC §21.2.1–2 | Tag exists. `test_spec_pin` fails if any frozen doc changes. |
| 1 | **Skeleton:** pyproject, `aew --version`, pytest config, CI matrix, and git/python preflight in `aew doctor`. | — | `pip install -e .[dev]`; `pytest` green on both OSes. |
| 2 | **Schemas + record I/O:** JSON Schemas (manifest, control, work-unit, plan, evidence kinds, decision, guardrails, gates, role) and a frontmatter reader/writer. | KC §6, §9, §11, §23 | Round-trip tests. Invalid docs are rejected with the path and reason. |
| 3 | **Persistence core** (`store.py`). | WC §5, §8.2; KC §12.3 | (a) Fault injection at every named point, in-process and via `os._exit` in a subprocess: the state is always revision N or N+1 and passes the invariant check. (b) 200 randomized crash iterations. (c) Two processes × 50 racing writes: revisions strictly sequential, no lost update. (d) Stale `--expect-rev` rejected. (e) Corrupt `control.yaml` → fail closed. |
| 4 | **Authority:** Lead acquire/handoff/takeover with terminal-based operator authorization, the token verifier scheme, and the role-permission matrix. | WC §5, §6; KC §7.2, §16 | Superseded Lead is rejected (`STALE_AUTHORITY`) through **both** the CLI and the Python API. A token issued in process A is verified in a separate process B. A tampered, revoked, or out-of-scope token is rejected: wrong role, wrong work unit, or an invocation token used for a control transition. **No raw secret appears in any file** under `.aew/` or any workspace (scan test). Role negatives: a Verifier submitting a classification, an Implementer submitting a review, a reviewer invocation equal to the implementer's, and a subagent attempting a control transition are all rejected. |
| 5 | **Work records + state machine:** Ticket create (Story/Epic records at schema level), deps, plan propose/accept (immutable, hash-pinned), BLOCKED/READY recompute, `status`/`work show|list|ready`, CURRENT.md + log. | WC §7, §8, §9.1, §9.6, §8.3; KC §9, §12.1, §18 | Table-driven tests of every legal and illegal transition. Editing an accepted plan → integrity error, and gates fail closed. `status --json` snapshot tests. |
| 6 | **Snapshot + workspaces:** git wrapper, fingerprint, worktree allocation with the strict serial cap, workspace-authority resolution, diff. | WC §8.1, §9.9; KC §9.5, §11 | Fingerprint matrix covering tracked edit, untracked, ignored, `include_ignored`, and `.aew` write (→ unchanged). Running `aew` inside a worktree resolves to the authoritative root, or refuses if the marker is missing. The cap rejects a second mutating assignment. |
| 7 | **Evidence, checks, gates, guardrails, classification:** `check run` (fingerprint before and after; a check that mutates inputs is INCONCLUSIVE), `submit`, review/verify ingest, `gate show`, `guardrails check`, `verify classify`. | WC §9.7–9.9, §10, §11, §12, §16.15; KC §8.11, §11 | The mapping from Ticket state to gates is enforced. Classification mapping tests. A guardrail violation blocks COMMIT_READY and integration. A review that touches a trigger path requires a specialty review gate. |
| 8 | **Context packs + launch contracts + role definitions.** | WC §5, §10.1, §15.4; KC §14, §15 | Packs are deterministic (same state gives byte-identical packs). The reviewer pack excludes rationale fields. Pack manifest hashes are recorded on the invocation. |
| 9 | **Dependencies + integration saga (ref CAS publish, worktree sync) + reconcile.** | WC §8, §8.1, §13; KC §9.5 | AT-2 passes. The ref is moved by a third party between validation and publish → the CAS fails, the candidate is marked stale, and M never appears on the authoritative ref. Crash points: after the `publishing` record, after the CAS, and mid-sync → reconcile reaches a consistent DONE plus a synced worktree, with nothing re-run. Dirty `.aew/` files survive the sync byte-for-byte. |
| 10 | **`init`, `authority accept/reject`, `resume`, `checkpoint`, `handoff`, `doctor`.** **`init` discovers candidates; it confers no authority** (plan review §4). Detected README, docs/, ADR dirs and contract paths are recorded as `authority.candidates` (path, suggested class, confidence, reason detected), and each candidate gets an OPEN-QUESTIONS entry. Only a Lead `authority accept <candidate> --class <contracts\|decisions\|schemas\|source\|orientation>` moves a ref into `authority.accepted`. This is a control transition plus a Decision record noting `decided_by: lead\|operator`. `project.yaml` is written through the engine, and its hash is pinned. Unaccepted candidates are never presented as authority in any context pack. Check commands start **unconfigured**, which blocks the check gates rather than guessing. | WC §15.5, §15.7; KC §6, §7.1, §19, §15.1 | `init` on a fixture repo with README, docs/ and docs/adr → zero accepted refs; all three are candidates with OPEN-QUESTIONS entries; nothing is duplicated. Accepting the ADR dir makes it appear in packs as authority; the README stays out. An out-of-band edit to `project.yaml` is detected. Resume golden test. Deleting `.aew/local/` loses no authority (KC §26 "cache loss"). |
| 11 | **Acceptance suite** (§6) run through CLI subprocesses with scripted roles. | WC §21.2.4–5; KC §26 | All of AT-1…AT-7 pass on Windows and Linux. |
| 12 | **M1 closeout:** ADRs 0001–0006, implementation-status table, operator quickstart. Staged: a manual live smoke of one Ticket using the generated launch contracts in a real harness. | WC Appendix C, invariant 18 | Status table reviewed. Every I/S/D claim links to a test or an explicit reason. |

---

## 6. Acceptance-test strategy

- **Layers:**
  - Unit tests for pure logic: transitions, gates, dependencies, guardrails, schemas.
  - Integration tests on real temporary git repos: fingerprint, worktrees, integration.
  - Persistence tests: fault injection, randomized crashes, multi-process races.
  - Acceptance scenarios run end-to-end through **CLI subprocesses**. This proves the CLI is the same authority as the API.
- **Scripted roles** (`tests/harness/roles.py`) use the same interface an LLM subagent would: the launch contract plus an invocation token. They produce deterministic outcomes: apply a patch, run checks, write a review with a scripted verdict or findings, and run acceptance and guardrail checks.
- **Operator-terminal steps** (AT-1, AT-4b):
  - On POSIX, the test runs the CLI under `pty.fork()` and types the challenge as the operator.
  - On Windows, a ctypes helper injects console input (`AttachConsole` + `WriteConsoleInputW`) into a CLI started with `CREATE_NEW_CONSOLE`.
  - If the Windows helper proves unreliable, that single step is reported as **skipped with a reason** on Windows and still passes on Linux, which is the target platform. It is never silently bypassed.
- **Fixture:** a tiny Python package with pytest tests. T-1 adds `subtract()`. T-2 depends on T-1 and adds a feature that uses it.

| ID | Scenario (maps to user brief / KC §26) | Key assertions |
|---|---|---|
| AT-1 | Serial lifecycle: `init` → Ticket + plan accepted → assign (bounded implementer pack) → implement + local checks → R1 review → verify (goal-backwards + contract) against the snapshot → COMMIT_READY → prepare → post-integration verify → publish → DONE. Then kill the Lead process, delete `.aew/local/`, start a fresh process, run `aew resume`, perform an **operator-authorized takeover** (the test acts as operator through a real pseudo-terminal), and complete a second Ticket. | Every artifact carries provenance (what/who/when/against/how/result/evidence). The resume output matches a golden file: objective, graph, accepted plan, no open findings, next action. No state lives outside the durable files. |
| AT-2 | Unintegrated dependency | T-1 COMMIT_READY → T-2 BLOCKED (reason: `T-1 not integrated`), and assigning it is rejected. T-1 published but a crash hits before DONE → T-2 is **still** BLOCKED. T-1 DONE → T-2 READY, and its assignment base contains M1. After the authoritative branch is artificially rewound below M1, assignment is rejected by the ancestry check. |
| AT-3 | Stale evidence | Verify passes on a dirty snapshot A. Writing the report into `.aew/` leaves the fingerprint unchanged. An uncommitted edit to `calc/core.py` → the review and verification gates are STALE, COMMIT_READY and integrate are rejected, and the V-A file is byte-identical and listed as historical. Re-review + re-verify on B → gates CURRENT. |
| AT-4a | Crash mid-transition | Every fault point, triggered via a subprocess `os._exit` → state is exactly the previous or next revision. The log and render are repaired. In-flight invocations → INTERRUPTED on takeover, never assumed complete. |
| AT-4b | Superseded Lead | A hands off to B. A writing with its old token → `STALE_AUTHORITY`. B writing with a stale revision → `STALE_REVISION`. The control file hash is unchanged after both rejections. **Self-authorization is impossible through any supported input:** a takeover attempted with invented flags, `AEW_*` env vars, `yes` piped to stdin, or an API boolean, all without a controlling terminal, is rejected with `OPERATOR_AUTHORIZATION_REQUIRED`, and the generation is unchanged. An operator-authorized takeover by C, answering the challenge on a real pseudo-terminal, bumps the generation. After that, **every** prior Lead token (A's and B's) and every prior in-flight invocation token is rejected. |
| AT-5 | Role separation | These negatives are rejected: a Verifier classifying, an Implementer reviewing, the same invocation reviewing its own work, a subagent making a control transition, and the Lead forcing VERIFIED from a failing record. |
| AT-6 | Lead-owned verification-failure classification (KC §26) | Each of the four classifications produces its mandated transition. |
| AT-7 | Workspace copies are never authority | `aew` inside a worktree cannot mutate from the worktree copy. An integration diff that touches `.aew/**` is blocked. |

---

## 7. Target status at M1 completion (WC Appendix C vocabulary)

These are targets, not claims. Each "Implemented" entry becomes true only when its linked tests pass (Step 12).

| Capability | Target status at M1 completion |
|---|---|
| Persistent/reconstructible Lead; crash-safe, stale-writer-resistant control state | **Implemented** |
| Knowledge Contract: manifest, resolver, current state, handoff, Ticket records, plan revisions, provenance, guardrail/build-test refs, `init`/`status`/`resume` | **Implemented** |
| Story/Epic records | **Staged** (schema, create, parent links). The roll-up, Story gates, closeout and promotion come in M2. |
| Parent-policy inheritance | **Implemented** as a function with unit tests. The full Story scenario is M2. |
| R1 context-independent review; independent verification; validation provenance; Lead-owned failure classification | **Implemented** |
| Concurrent mutation isolation | **Staged**: per-Ticket worktrees exist, but the cap is hard-coded to 1. Concurrency > 1 is M5. |
| Dynamic scheduler | **Designed** (M5) |
| Command/skill interaction layer (`/aew ticket`, ...) | **Staged**: CLI primitives are implemented; the OpenCode adapter is M3. |
| OpenCode provider path, GPT-5.4 routing, R2 review | **Designed** (OpenCode is the first target, M3) |
| Lease-expiry automatic Lead takeover (atomic new authority epoch) | **Designed** (future ADR; D-op-3) |
| Workbench Capability Contract, provider health, MCP adapter over engine | **Designed** (M6) |
| Build/test impact analysis, SCM/Jira, security triggers beyond path rules, freshness automation | **Designed** |

---

## 8. Specification ambiguities, contradictions, blockers

**A. Genuine semantic gaps, now RESOLVED by operator decision.** These are implementation-level decisions, recorded as ADRs. They do not bump the contract version.
1. **Post-integration validation failure and integration conflict.** WC §8, §8.1 and §13 require validation before DONE but do not define what happens when it fails. **Resolved (D-op-2):** validate-before-publish, as described in 4.7.
2. **Takeover when the prior Lead is unreachable.** WC §5 and KC §7.2 require an explicit transfer, but neither names who may authorize one that isn't cooperative. **Resolved (D-op-3, tightened by review):** only out-of-band operator authorization counts. In M1 that is confirmation on the controlling terminal; a flag, reason or boolean never authorizes. Lease-expiry auto-takeover with an atomic new authority epoch is **Designed** for a future ADR. If you think the contract itself should say who may authorize a takeover, note it as a candidate amendment for the next spec version.

**B. Wording tensions, resolved without new semantics (recorded in ADRs):**
1. WC §8 says the "Verifier records VERIFIED/…", while control state is Lead-only (WC §5, KC §7.2/§16). Resolution: the Verifier owns the result in its evidence, and the Lead's ingest applies the state that result mechanically determines.
2. The verification result `blocked` (WC §6, §9.9) has no Ticket state. It maps to VERIFICATION_INCONCLUSIVE(result = blocked), and never to the dependency state BLOCKED.
3. ENVIRONMENT_OR_EVIDENCE_BLOCKED "remains blocked/inconclusive". It goes to VERIFICATION_INCONCLUSIVE with the classification attached, and its only exit is back to VERIFY_PENDING.
4. WC §8 says a mutating Ticket reaches DONE "by default" only after integration, but the transition list states this unconditionally. It is treated as unconditional for mutating Tickets.
5. The "typical" state model leaves some transitions out, including regressions on stale evidence and INTERRUPTED exits. These are filled conservatively (4.3, ADR-0003).
6. What "mutating concurrency = 1" counts is undefined. Choice: a Ticket counts while it holds a live unintegrated workspace.
7. SPT-R §9.4 says "mark imported items here as migrated", which conflicts with the manifest freeze rule. Resolution: leave the frozen appendix unedited, and record the migration in `docs/implementation/spt-remediation-migration.md` plus the provenance on the AEW Epic.
8. WC §23 numbers invariants 11–13 twice. This is editorial only; the invariants are cited by name.

**C. Environment/input blockers (SPT only; none block AEW M1):**
1. ~~SPT repo identity / missing explorer~~ **Resolved (D-op-1, corrected).** The SPT target is `security-platform-toolchain`. The explorer exists internally and was never committed externally. A5 evaluates it, then adopts, ports, or replaces it. It needs its source supplied, and until then the Git CLI is the fallback.
2. **Still open:** the Ghidra bridge environment variables must come from the audited environment (SPT-R §4.2), and that environment is not in the repo. SPT-R P0-4 (Ticket C1) stays BLOCKED until you supply it. This affects SPT only.
3. The SPT working tree holds uncommitted WIP on `python-whl-1.2`. No SPT changes will be made until it is committed or stashed.
4. OpenCode, GPT-5.4 and Rocky 8 are not available here. The M1 core is harness-neutral. OpenCode will be installed locally before M3 (D-op-4). Rocky 8 validation is SPT B2/B4.

---

## 9. SPT: reuse, remediation work, dogfood import

**Reuse as-is:**
- `images/gitnexus`: engine, MCP, and the offline Ladybug patch.
- `images/ghidra-base`, `images/ghidra-mcp` (bridge/headless), and `ghidra-exporter` headless modes.
- The `scripts/doctor.sh` reporter.
- `common/emit-artifact-manifest.py` and `scripts/release-provenance.py`, for sha256 and provenance records.
- The `scripts/artifact-cache.sh` content-addressed pattern.
- The py311 wheelhouse, which already covers AEW's deps.
- `images/diff-impact` is **not** a repository explorer and will not be relabelled as one.

**Remediation work.** Imported as Epic "Toolchain Readiness", with Stories per SPT-R §9, P-priorities preserved and provenance pointing to SPT-R sections. D = discovered during inspection.

| Story | Tickets |
|---|---|
| **A. GitNexus durability/permissions** | A1 (P0-1) persistent HOME/registry/index volume; derived-state metadata (project/worktree id, source revision, GitNexus version, config) + stale detection. Acceptance per SPT-R §2.1: index → stop → edit/delete as work user → restart → reuse. A2 (P0-2) run as the effective host UID/GID; no hard-coded user; no recursive chown of source. A3 (D) remove or guard the `GITNEXUS_FIXTURE_REPO` `rm -rf /workspace` hazard. A4 (D) fix the stale `clone`/`upload` callers and the unused compose `NEXUS_*` env; create the missing `examples/gitnexus-*-smoke` directories to serve as the acceptance harness. A5 (P1-8, per corrected D-op-1): **evaluate the existing internal lightweight Python explorer**, then choose one of: adopt it as-is, generalize/port it, or replace it if it is unsuitable or unavailable. Evaluation needs you to supply its source. Until then, `repository_exploration` resolves to the Git CLI as the guaranteed fallback, with the internal explorer as a candidate provider and GitNexus as the richer relationship/impact provider. The explorer must **never** claim GitNexus relationship or impact semantics and is not "GitNexus Lite". Whatever is adopted is packaged with the py311 toolchain and registered in the D2 manifests. |
| **B. Container UID/GID + runtime packaging** | B1 (P1-5) reusable UID/GID startup pattern in `common/`, generalized from A2 and applied only to managed paths. B2 (P1-7) Rocky 8 bundle import + `verify-offline` + functional smoke, pinning base distro, arch, versions and digests (SPT-R §6). B3 (D) root-running images fail `container-structure-test`: resolve the allow-list vs `USER`. B4 (D/new) package AEW for the offline Rocky 8 host. B5 (P2-9) base-distro optimization, only after the rest is stable. |
| **C. Ghidra remote artifact + binary-analysis bridge** | C1 (P0-4) capture and package the audited bridge environment (**blocked** until you supply the audited environment; §8 C2). C2 (P0-3) `remote_artifact_acquisition`: an allow-listed controlled SSH/scp retrieval that records host, path and source ref. C3 `binary_artifact_staging`: hash + persistent staging store + provenance record. C4 `binary_analysis`: ghidra-mcp consumes the staged artifact, with a persistent project volume instead of `/tmp` + `-deleteProject`; fix the exporter's 8080/8089 port mismatch. Acceptance per SPT-R §4.2: select → stage → hash → analyze → MCP query → restart → persistence/provenance. **`function_analysis` is not touched.** |
| **D. Doctor/offline validation** | D1 (P1-6) extend doctor with GitNexus service, writable mount and persistence; repo explorer; Ghidra MCP; Ghidra staging. The browser, memory and provider-gateway services don't exist in this repo, so those checks report **UNAVAILABLE** (visible absence per WC §16.10), never a fake PASS. D2 Staged Workbench Capability manifests for these providers (SPT-owned YAML; AEW-owned resolver in M6). |

Dependencies: A2 → B1; A1 ∧ A2 → D1(GitNexus); C2 → C3 → C4; C1 → C4; B4 → running AEW on Rocky.

---

## 10. After M1 (ordering)

- **M2:** minimum Story/Epic path (roll-up, Story gates and closeout, parent-policy scenario, Ticket→Story promotion, non-mutating Ticket path). The SPT import needs this (SPT-R §9 requires Epics/Stories/Tickets).
- **Dogfood import:** `aew init` on SPT, which maps README, docs, FUTURE_WORK and KNOWN_LIMITATIONS as authority refs. Import §9, write the migration record, and from then on the Work Graph is the backlog authority.
- **M3:** the **OpenCode** adapter (D-op-4):
  - `/aew ticket|story|epic|status|resume|review|verify|checkpoint|handoff` commands mapped to CLI primitives;
  - Lead and role agent definitions generated from `roles/*.yaml` and the launch contracts;
  - subagents receive invocation tokens only.

  Prerequisite: you install OpenCode locally, preferably in WSL. Verification is a live run of AT-1's Ticket with a real OpenCode Lead, subagents, session destruction, and resume. After that, execute the SPT Tickets through AEW. Porting to the Rocky 8 VM and GPT-5.4 follows once packaging is done (SPT B4).
- **M4/M5:** isolation with concurrency > 1 (integration queue, merge revalidation), then the dependency-aware dynamic scheduler.
- **M6:** capability manifests + resolver + provider health in `doctor`; an MCP adapter over the same Engine API.

---

## 11. Verification (how to run)

- **Windows:** `py -3.13 -m venv .venv; .venv\Scripts\pip install -e .[dev]; .venv\Scripts\pytest -q`
- **Linux:** clone into WSL ext4 (`~/src/aew`, not `/mnt/c`), then `python3.11 -m venv .venv && .venv/bin/pip install -e .[dev] && .venv/bin/pytest -q`
- **Acceptance only:** `pytest tests/acceptance -q`. AT-4a includes the subprocess `os._exit` crash matrix.
- **Manual smoke:** `aew init` in a scratch copy of `tests/fixtures/sample_project`, then `aew status`, `aew resume --json`, and `aew doctor`. Follow the AT-1 command sequence documented in the quickstart.
