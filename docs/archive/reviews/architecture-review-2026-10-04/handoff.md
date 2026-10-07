# Handoff: AEW architecture review, where to resume

Written 2026-10-04 after `REVIEW.md` in this directory was delivered. Purpose: let a later session (mine or another reviewer's) continue the design deep-dive without re-reading 1.7 MB of documents from scratch.

## 1. What this directory holds

| Path | What |
|---|---|
| `REVIEW.md` | The ground-up architecture review (about 8,000 words): §1 state, §2 twelve ranked gaps G1 to G12, §3 twelve improvements I1 to I12, §4 tech stack / MCP / skills upgrades, §5 whole features F-A to F-K, §6 the three M6 knowledge drafts (issues K1 to K9), §7 sound, §8 sequencing, §9 process |
| `tree/` | Frozen clone of `JonSmithTLT/Agentic-Engineering-Workflow` at `dcd43f1` (branch `docs/restructure`, "Docs: a map and a structure by status"). Origin is the local checkout `Documents/GitHub/Agentic-Engineering-Workflow`; never write there |
| `extra-docs/` | The three untracked M6 knowledge drafts, copied from the live checkout's working tree (they were `??` in `git status` on 2026-10-04): capture/admission v0.3, recall/context-routing v0.2, shared semantics v0.3. `SHA256SUMS` pins what was reviewed; `PROVENANCE.txt` says where they came from. If they have since been committed or revised, diff against these hashes first |
| `ADR-0012-transaction-outbox-draft.md` | **T3 delivered (2026-10-04):** the outbox ADR draft. The outbox is the existing transition log, declared complete, given typed `events` derived in the store, a revision-number cursor, a wake file, sealing into 256-record segments, and an optional hash chain. See §8 below |
| `repro/` | The two probes behind the T3 draft and their outputs: `log_growth_probe.py` (one log record per revision for every commit kind, never pruned) and `log_recovery_probe.py` (a crash at `txn.after_replace` / `txn.after_apply` is repaired by the next read). `repro/work/` is the throwaway project they build; `token.txt` carries the Lead token between them |
| `.venv/` | A venv with `tree/` installed editable (`pip install -e ./tree[dev]`), used by the probes. Not part of the review record; delete freely and recreate the same way |
| `T1-typed-lead-surface-design.md`, `T1-typed-lead-surface.patch` | **T1 delivered (2026-10-04):** the typed Lead surface design note and the prototype (branch `review/t1-typed-lead-surface` in `tree/`, one commit, exported as the patch). The contract (`aew.surface`) sits below transport; `aew lead mcp` is the MCP transport; `aew lead tool` is the CLI parity adapter. See §9 below |
| `HANDOFF-addendum-designer-2026-10-04.md` | The designer's addendum (verbatim): T9 and T10 added, a triage of all remaining threads requested |
| `TRIAGE.md` | **The answer to the addendum:** every remaining thread classified and ranked, with the next two to four pieces of work (§3). Read it before the notes below |
| `ADR-0013-knowledge-storage-placement-draft.md` | **T4 delivered (overnight 2026-10-04); approved by the designer with terminology edits:** knowledge records as five new entry kinds of the ADR-0011 manifest; probe `repro/knowledge_manifest_probe.py` (+ `.out.txt`). See §10 |
| `T4-knowledge-manifest-prototype.md`, `T4-knowledge-manifest.patch` | **T4 prototype (2026-10-04):** branch `review/t4-knowledge-manifest` in `tree/` (from `dcd43f1`): the schema change, record schemas, `about`/`current`/FTS `search` in the index, `aew knowledge case|dispose|show|list|search`, the full audit's knowledge checks, oracle rule 29, 14 tests. The Lead commits (D9's service identity is not modelled). See §13 |
| `T4-D9-service-identity-spike.md`, `T4-D9-service-identity.patch` | **D9 spike (2026-10-04, after the designer accepted ADR-0013 Q1):** branch `review/t4-d9-service-identity` on top of the T4 prototype: the `service` credential kind, `knowledge_service` issued/rotated/revoked by the Lead, `service_txn` beside `lead_txn`, the closed `knowledge.*` family enforced by the control store at commit, no archival in a service commit, custody as for the Lead. 8 tests (the operator takeover through a pty on the VM). The smallest ADR-0005/ADR-0009 amendment is written out. See §16 |
| `T6-network-containment.md`, `repro/t6/` | **T6 delivered:** network namespace, bridge, forwarder, egress proxy and OpenCode startup probes on the real Rocky 8.10 kernel, plus the F-F design candidate and register text. See §10 |
| `T6-register-entry-and-adr-0009-amendment-draft.md` | **T6 artifacts (2026-10-04; direction accepted by the designer the same day, final text in §2):** the register row (F21 placeholder, §2 format) and the full ADR-0009 amendment text for network containment, written against the live branch's M4-B amendment: it closes M4-B's documented residual for the provider key (not the server password), adds `network: proxy_only | shared | not_provided`, policy, self-test, checks setting, schema/code deltas and six decisions. See §15 |
| `T9-harness-native-integration.md` | **T9 delivered:** the OpenCode/Codex capability matrix, per-harness MUST/SHOULD/OPTIONAL/DO-NOT-USE/PROBE profiles, adapter seams, the first support target. See §10 |
| `T9-live-probe-1-results.md`, `repro/t9/` | **T9 live probe 1 (and T1's live spawn), run on the VM against real OpenCode 2.0.18:** Code Mode hides MCP tools by default; `codemode: false` exposes them (12 tools = 11,178 bytes); a permission `deny` removes a tool's schema from the model request; a built-in 45-tool `browser` namespace rides along with `execute`; a failed MCP server is silent. The captured model requests are `repro/t9/request_V*.json`. The T1 branch gained a second commit (`codemode: false`; patch regenerated). See §11 |
| `T7-amendment-index.md` | **T7 delivered:** every amendment and the frozen sections it touches; `docs/spec-amendments.yaml` candidate; citation test sketch; re-freeze sizing |
| `T7-citation-test-results.md`, `repro/t7/` | **T7 citation test run (2026-10-04):** the sketch's test over the living documents at `dcd43f1` and the live branch: the index touches a third of all contract citations; the naive rule flags 13 (12 noise); the refined topic rule flags exactly one, a real defect (`acceptance.md` AT-9 still describes the frozen KC §26 case its own test refuses). Check 3 is noise; drop it. See §14 |
| `T2-evaluation-component-plan.md` | **T2 delivered:** F19 package layout, `aew/eval-run/v1`, the preregistration record, the hidden-evaluator channel, the corpus list, the comparator as a verification item |
| `T10-install-bootstrap-ux.md` | **T10 delivered:** onboarding survey, the install → init → doctor → launch workflow, the configuration-ownership model, connected and air-gap profiles, doctor rows, non-goals |
| `T5-project-maps.md` | **T5 delivered (bounded):** deterministic codebase map record, freshness by the discovery-record rule, `aew map` commands, storage in ADR-0013; pack budgets left to evaluation |
| `T5-codebase-map-probe-results.md`, `repro/t5/` | **T5 probe (2026-10-04):** the §2 codebase map generated from Git objects only on three repositories: 0.1 s and 3.5 KB without the Python import graph, 0.6–0.75 s and 28 KB with it; byte-identical for the same commit from two checkouts on different branches; deterministic across repeats. Two corrections: `ls-tree` at the commit, not `ls-files` (index-bound: 809 vs 930 files for one commit); freshness can be listing-plus-config scoped (CURRENT through 21 of the last 30 main commits instead of 0). The fixed role table leaves 2 of 7 (AEW) and 8 of 13 (SPT) top-level directories `unknown`. See §17 |
| `S1-cxx-semantic-extraction-investigation.md`, `repro/sem/` | **S1 (2026-10-04, second brief):** C/C++ semantic extraction from `compile_commands.json` with Clang 21 on Rocky 8, measured against the build's own objects on zlib and curl: definitions and linkage 100%, includes 100%, direct call edges 99.4–99.5%, every discrepancy in three categories (compiler-synthesized `memcpy`, builtin-inlined libc, constant-folded branches); dispatch tables in global initializers are where C's indirection lives (754 refs in curl's lib). Three tiers: compiler-known / static inference / unsupported. 0.1 s per TU. See §18 |
| `S2-S5-semantic-extension-framework.md` | **S2–S5:** the shared extension contract (fact kinds with tiers, unit = TU not file, extractor identity, per-unit freshness from input sets, two coverages, deduplicated artifact as an ADR-0013 `reference` record, generated limitations), the `map.*` typed surface with measured answer sizes (55–450 tokens single-hop, 6–11k at radius 2, graph 33M), incremental rebuild from `clang-scan-deps` fan-out (median header 21 of 434 TUs, six reach all), and the deterministic-map → semantic → investigator bridge. Five decisions for the designer |
| `S6-query-routing-and-retrieval-classification.md` | **S6 (a security-research platform as prior):** a six-class taxonomy by binding × answer shape, a five-stage router with measured-gap escalation and four terminal states (`SATISFIED`, `EXHAUSTED_BUDGET`, `NOT_FOUND`, `NOT_SUPPORTED`), the cheap observable signals, failure behaviour, an evaluation plan with negative controls and cost accounting, and six implications for T5/S2–S3 (the typed surface is Stage 1; radius is the budget dial) |
| `S7-large-repo-benchmark.md`, `repro/t5/synthetic_repo_bench.py` | **S7:** synthetic 10k/100k-file repositories: structural map 0.28 s / 18 KB and 2.1 s / 162 KB, `ls-tree` 0.3 s, diff 18 ms at 100k; C semantic cost extrapolated from S1's constants (50k TUs ≈ 2 h single-core first build, minutes incrementally). Verdict: no sharding or index for the structural map; incremental model and a derived index for the semantic map from day one |
| `S8-project-understanding-profile-and-impact-analysis.md`, `repro/ria/` | **S8 (third brief, Parts A–E):** the layered hypothesis survives with two corrections: the Project Profile is KC §8's maps plus WC §16.15 guardrails as evidence-bound records with per-claim freshness (no new layer, no document set); impact analysis is the deterministic supplier of plan assurance v0.4's first-pass inputs and premise list (no new artefact). Probe: a seed → symbols → radius-1 → tests/rules/schemas/ADRs surface scored against three real changes: recall 1.00 at radius 1 for the two localized requirements, 0.54 for the cross-cutting one, precision 0.1–0.6; created files are the ceiling of any location method. Nine deliverables, five designer questions, T5 v0.4 hooks separated from later work |
| `S1b-cxx-plus-plus-contract-check.md` | **C++ probe (fmt 11.0.2, 49 TUs):** the designer's acceptance question answered item by item (templates/instantiations, overloads, namespaces, inline/ODR, methods, virtual dispatch, member pointers, template-heavy headers, cross-TU identity). The identity/provenance/coverage/freshness/evidence/relation model holds with two shared additions (instances under a template symbol; `dependent` and `virtual` edge kinds); extraction *fidelity* for instantiation-level edges needs a codegen-adjacent source (LLVM IR), which is an extractor identity inside the contract, not a hack. Numbers in the note |
| `T8-remote-integration-target.md` | **T8 sketch only (wait for designer question 8):** `integration.target`, the saga with an observed merge, the provider adapter interface, what M4-D should not foreclose |

Earlier reviews in this series, for cross-reference: `../AEW-M4-area2-authority-a6cdc64/`, `../integration-publication-a6cdc64/`, `../control-state-persistence-a6cdc64/`, `../dispatch-legality-a6cdc64/`, `../m4b-containment-a9fabaf/` (its F1 and F2 are I1 and I2 in `REVIEW.md`).

## 2. How to get oriented fast (reading order, about 40 minutes)

1. `tree/docs/README.md`: the map and the governing order.
2. `tree/docs/implementation/implementation-status.md` and `future-work.md` §1, §2, §4: what is built, the register, the open questions.
3. `tree/docs/implementation/m4-ambiguity-report.md` §2 (architecture) and "M4-A as built".
4. `tree/docs/archive/milestones/m3-evidence-synthesis.md`: the dogfood evidence in six pages.
5. `REVIEW.md` §1 and §2.
6. For the knowledge system: `extra-docs/aew-knowledge-capture-recall-shared-semantics-v0.3.md` first (shortest, defines the vocabulary), then the other two; then `REVIEW.md` §6.

The frozen contracts (`agent-engineering-workflow-design-v0.7.md`, `aew-knowledge-contract-v0.4.md`) are only needed when checking a specific section; `REVIEW.md` cites them by section.

## 3. Facts established in this review that a deep dive should not re-derive

- Dogfood numbers (M3): plain OpenCode 20/20; AEW 24/26 (12/12 with Sol); cost 6.5x (Luna) to 7.5x (Sol); Lead about 40% of cost; median 20 workflow commands and 34 steps per Lead session; 51 of 887 `aew` commands refused (`ILLEGAL_TRANSITION` 32); independent review caught the seeded defect 19/19; resume after harness loss 3/3; one harmful outcome (T4, acceptance-input mutation).
- ADR-0011 P3 verdicts: H1 1.05x (flat) / 1.08x (hierarchy); history 7.6% of hot state at 20 open / 3,000 completed; H2 +0.024 s paired; H3 13.3 ms Windows, 7.0 ms Rocky; A1 about 1 KB and 3.1 ms per open unit on Windows.
- Code shape at `dcd43f1`: about 20 k lines in `src/aew`; 14 JSON schemas; about 70 CLI subcommands; 78 test files; coverage about 92% lines / 82% branches at M4-A; 302 commits since the 2026-09-25 freeze.
- Context packs (`src/aew/knowledge/context.py`) carry: contract, card, requirement, hierarchy, plan, inputs, subject, children, loaded history, guardrails, authority, checks, findings, diff. They carry no codebase or architecture map (`manifest.py` defaults those knowledge entries to `null`).
- The OpenCode projection (`harness/opencode/projection.py`) already has `provided_skills` plumbing and a `skill` allow rule; M3 provides none.
- Dispatch: nine registered entrypoints in `engine/dispatch.py`; `engine/reasons.py` is the one reason-code registry; `engine/primitives.py` declares dispatch and integration primitives (undeclared = `JUDGMENT_BEARING`).
- The Lead broker relays `lead.cli {argv, cwd, stdin}` and `lead.whoami`; the run bridge has exactly `whoami`, `check.run {check_id}`, `submit {kind, text}`. Both are the natural seams for an MCP surface (G2).

## 4. Threads to dive deeper on, in the order I would take them

Each names what a deeper session should produce and what to read first.

| Thread | Produce | Start from |
|---|---|---|
| **T1. Typed Lead surface (G2, F-A)** — **delivered, see §9** | A design note: tool list (stages plus `cli(argv)`), result shape (`ActionProjection`), where the MCP process runs (broker side; thin client inside the sandbox for roles), retry rules for `MECHANICAL` primitives on `STALE_REVISION`, custody argument, context-cost mitigation (deferred tools) | F15 idea note §3 to §5, §15; ADR-0009 "the Lead is symmetric"; `lead_broker.py`, `bridge.py`, `projection.py`; the airgap research §5 (OpenCode MCP, tool filtering) |
| **T2. Evaluation component (G1, F19)** — **delivered, see §10** | A plan: package layout, `aew/eval-run/v1` schema, preregistration record, hidden-evaluator channel, incident corpus list with sources, external comparator choice (verify against the gateway) | decisions record §3.6; plan assurance v0.4 §28 to §30; `eval/m3/dogfood/README.md`, `rubric.md`; F17 §8; skills `evaluation-guide.md` |
| **T3. Transaction outbox (G11, K2)** — **closed, see §8** | An ADR draft: record shape, ring size, archival rule, consumers (wait-any, dashboard SSE, knowledge capture, scheduler), crash semantics under ADR-0001 redo staging | ADR-0001, ADR-0011 R8 (`Session.prewritten`), `engine/seams.py` (`TxnFinalizer`), `engine/store.py`; the capture draft §7 to §8 |
| **T4. Knowledge storage placement (K1)** — **delivered, see §10** | An ADR draft placing knowledge records in the ADR-0011 manifest: new entry kinds, `history.schema.json` changes, FTS in `local/history.sqlite`, audit coverage; or the argument for a second store | ADR-0011 "Decision"; storage investigation §3; `history/{store,manifest,index}.py`; shared-semantics draft §4, §17 |
| **T5. Project maps (G3, F-B)** — **delivered (bounded), see §10** | A design note: codebase map generator (deterministic), architecture map (investigator Ticket), freshness via `observed_paths`, pack sections and budgets, `aew map` commands | KC §8.2 to §8.5, §13; ADR-0008 freshness; `knowledge/context.py`, `knowledge/manifest.py`; Lead/operator design §5 to §7 |
| **T6. Network containment (G5, F-F)** — **delivered with live probes, see §10; artifacts drafted, see §15** | A probe plan for the Rocky VM: `--unshare-net`, a unix-socket egress proxy bound into the sandbox, what OpenCode 2.0.18 fetches at startup, label vocabulary change | containment research §3.2, §8; `harness/containment/layout.py`; my area-1 `repro/contain_probe.py` as a lab template |
| **T7. Re-freeze and amendment index (G6)** — **delivered, see §10; test run, see §14** | The list of amended sections across WC/KC with their amendment documents, and a test sketch | `docs/README.md` "What governs"; `spec-pin.yaml`; the two amendments; Ticket-revision review §7 |
| **T8. Remote integration target (G10, F-G)** — **sketch only, waits on question 8** | ADR-0004 amendment sketch: `integration.target`, provider adapter interface, `DONE` on observed merge, reconcile changes | ADR-0004; `engine/integration_ops.py`, `workspace/integration.py`; WC §13 |
| **T9. Harness-native integration strategy** (designer addendum) — **delivered, see §10** | Capability matrix for OpenCode and Codex, per-harness integration profile, adapter seams, the first support target | the addendum; `harness/{base,contract,registry}.py`, `harness/opencode/*`; the pinned 2.0.18 OpenAPI; current OpenCode and Codex documentation |
| **T10. Installation, bootstrap and integration UX** (designer addendum) — **delivered, see §10** | Onboarding survey, install → init → doctor → launch, configuration ownership, connected and air-gap profiles, upgrade and rollback, doctor rows, non-goals | the addendum; `guides/quickstart.md`, `guides/opencode.md`; `doctor.py`; `knowledge/discovery.py`; T6 and T9 results |

Threads T1 and T3 are the highest leverage; T4 is the one the knowledge drafts cannot be adopted without. `TRIAGE.md` ranks what remains.

## 5. Questions I would put to the designer

1. Is an MCP transport for the Lead acceptable as the F15 delivery vehicle, or must stages ship as CLI first (WC §15.6 allows either; invariant 21 is satisfied by both)?
2. Should knowledge records join the ADR-0011 manifest (one chain, one audit) or get their own store?
3. Visibility scope in the knowledge drafts: project-only in v1?
4. Will F19 be a code component, and does it live in this repository or beside `aew-private/eval`?
5. Is a second harness adapter wanted before M6, and which (Codex app-server or Claude Code headless)?
6. Network containment: a sibling register entry to F2, or part of internal-alpha acceptance?
7. When is the v0.8/v0.5 re-freeze?
8. Is a remote (PR) integration target in scope before internal alpha?

## 6. Checks before relying on this review again

- `git -C tree rev-parse HEAD` must be `dcd43f1901b9999ec65ae6c84490e319384861df` (branch `docs/restructure`). The T1 prototype is the local branch `review/t1-typed-lead-surface` (`af72ec5` + `084e3fa`, two commits on top; `T1-typed-lead-surface.patch`) the T4 prototype is `review/t4-knowledge-manifest` (`a9a9cd9`, one commit on top; `T4-knowledge-manifest.patch`) and the D9 spike is `review/t4-d9-service-identity` (`d9a9645`, one commit on top of the T4 prototype; `T4-D9-service-identity.patch`): check one out to run its tests, and return to `docs/restructure` afterwards so this check holds. The venv runs whatever `tree/` has checked out.
- `sha256sum -c extra-docs/SHA256SUMS` must pass; if the live checkout's copies changed, re-read the diff before reusing §6.
- `main` and `docs/restructure` may have moved: `git -C tree fetch origin && git -C tree log --oneline dcd43f1..origin/main` shows what landed since. M4-B (`a9fabaf`) was on a PR, not merged, at review time.
- Nothing in this review was reproduced by running code. Any finding that becomes a work item should be reproduced in a fresh checkout under this directory first, following the area-review pattern (`repro/`, logs beside it).

## 7. Constraints that still apply

Own checkouts only (this directory); the live `Agentic-Engineering-Workflow`, `AEW-tooling` and `AEW-web` checkouts are read-only. VM work only under `~/aew-review`, own venv, no sudo, hold pytest while the lead developer's suite runs, clean `~/.aew-test-tmp/review-*` afterwards. Do not read `aew-private` or triage notes for an area before writing its findings.

## 8. T3 closed: the outbox draft was reviewed as a strong approve with minor fixes (2026-10-04)

Delivered `ADR-0012-transaction-outbox-draft.md` with two reproductions. Facts established there that T1, T4 and the M4-D planner should not re-derive:

- `state/log/<rev>.yaml` is written for every commit by `ControlStore._post_commit`, including the five commit sites that bypass the transaction finalizers (`lead.acquire`, `lead.handoff.accept`, `lead.takeover`, `harness.{stop,send,interrupt}`, `migrate`). An outbox attached as a finalizer would miss four of them; the draft therefore derives events in the store.
- The log is complete after a crash: recovery re-runs `_post_commit`, and the repaired record equals `last_transition` (probe 2, both fault points). Nothing prunes it (probe 1); the storage investigation measured 60,000 files at 3,000 Tickets.
- Run status is not a committed fact: the supervisor writes `local/harness/runs/<run>/run.json`, and a run's end moves no control state until the Lead ingests it (WC §8.2). The draft keeps that lane out of the outbox (D5) and combines both lanes in wait-any; whether a supervisor may ever commit is an open authority question for the designer.
- Decisions the draft leaves to the designer are listed in its "Not decided here": the window size, the chain (D7), the surface name, the dashboard transport, supervisor commits, and where the capture worker's cursor lives (which is T4's K1 question).

Follow-ups this thread did not do: a register row for the outbox (proposed E15) and the E1 pointer in `future-work.md`; the dashboard contract addition (`/events`) and its C0 renewal; a note on the storage investigation's "sharding not required" decision. All belong in the live repository, which this review does not write.

## 9. T1 delivered: the typed Lead surface (2026-10-04)

Delivered `T1-typed-lead-surface-design.md` and a prototype on branch `review/t1-typed-lead-surface` of `tree/` (commit `af72ec5`; patch beside it; `tree/` is left on `docs/restructure`). Facts established that later threads should not re-derive:

- The pinned OpenCode 2.0.18 OpenAPI spells MCP configuration `Config.InfoEncoded.mcp.servers.<name> = {type: "local", command: [...]}`, and `Mcp.Protocol` "legacy" speaks revisions up to 2025-11-25. The public documentation describes a newer shape. Follow the pinned schema; the prototype's capability probe now checks these keys.
- The Lead broker's `_run_cli` is now a module function (`lead_broker.run_cli`) so the `cli` tool and the `lead.cli` operation share one definition of the primitive surface; the broker gained `lead.tool {name, arguments}`.
- Context cost of the surface as built: 12 tools, 11,711 bytes compact, about 2,900 tokens; the 5.5 KB result schema is not advertised per tool.
- Test evidence: 17 unit and 2 end-to-end tests pass (a real `aew lead session`, the fake harness launching a run through `ticket_start`); the unit lane plus the OpenCode, M3-defect and M4-dispatch regressions pass (808); the Lead-session, dispatch-conformance and harness suites pass (47); ruff clean; pyright no errors. Only the Lead projection golden changed, by the three intended additions.
- Not built, stated in the note §9: `ticket_prepare`, the stage-intent journal, `STALE_POLICY`, queryable transition and ingest guards, policy-resolved review card sets, wait-any, the `aew-run` role server, a live spawn check against 2.0.18.

Open for the designer: the six questions in the note's §12 (two-tool acceptance, exposing `cli`, `auto_runnable` default, direct mode, journal timing, server naming).

Suggested next thread: T4 (knowledge storage placement), which both the outbox draft (D11 question 6) and the knowledge drafts wait on; or T2 (evaluation) if the dogfood instrument for F15 is wanted before M4-E.

## 10. Overnight 2026-10-04: T4, T6, T9, T7, T2, T10, T5 delivered; T8 sketched; the triage written

The designer's addendum (saved as `HANDOFF-addendum-designer-2026-10-04.md`) added T9 and T10 and asked for a triage. `TRIAGE.md` is the answer and the entry point; each note is listed in §1. Facts established overnight that later work should not re-derive:

- **T4 (ADR-0013 draft).** The history manifest accepts knowledge entry kinds with a one-line schema change; everything else (chain, verification, index, `by_id`, `linked`, `list`) works on unchanged code (`repro/knowledge_manifest_probe.out.txt`). The index's `annotations(subject)` is kind-bound and `History.unreferenced` is glob-bound: both need one generalisation. Costs at 6,006 entries: 977 ms per 100-record commit (9.7 ms per file, Windows fsync), 0.32 ms per 1 KB record in a full verification, 0.9 s index rebuild, FTS5 present in the venv's SQLite with single-digit-millisecond queries. The shared semantics' `knowledge_event_seq` is the manifest `seq`; the capture cursor is derived from receipts. One designer question blocks M6b planning: a non-Lead committer for a closed `knowledge.*` transaction family.
- **T6 (network containment, real Rocky 8.10 kernel).** `--unshare-net` works; the filesystem AF_UNIX bridge survives it, an abstract socket does not; the supervisor reaches the server through an in-sandbox forwarder at 0.7 ms per request; an allowlisting proxy on a unix socket keeps the provider key outside the sandbox and the Bun runtime honours `HTTPS_PROXY`; OpenCode 2.0.18 `serve` starts with no network and its only startup fetch is `models.opencode.ai`; offline, the embedded catalog lacks models newer than the binary (`gpt-6.1-*` absent), so air-gap needs a seeded `opencode.db`; slirp4netns fails `setns` from outside bubblewrap. Outputs in `repro/t6/`.
- **T9.** The pinned 2.0.18 API and the public OpenCode documentation differ in paths, permission shape, MCP config shape and config keys; Codex documentation moved to `learn.chatgpt.com` (308 redirects) and `codex mcp-server` was removed in favour of the experimental `app-server`. Capabilities must be recorded per adapter per pinned version. Six live probes are named; two run.
- **T7.** Frozen sections with replaced text: WC §7.4, §7.5, KC §26 (one case). Sections an adopted decision says must be amended and are not: KC §12, WC §7, §8, invariant 7 (Ticket revisions). 36 distinct contract sections are cited 80 times by living documents; KC §26 (9) and WC §7.4 (3) are both amended.
- **T2, T10, T5, T8:** plans and sketches; no new facts beyond what the notes cite.

VM state after the session: `~/aew-review/t6-net` holds the probe scripts and outputs (kept); `~/.aew-test-tmp/review-*` removed; nothing under `~/aew-m4` touched; no probe process left running. `tree/` is still on `docs/restructure` at `dcd43f1`.

Open for the designer, collected: ADR-0013 Q1–Q5; T6 Q1–Q4; T5 Q1–Q3; T2 Q1–Q3; T10 Q1–Q3; T8 Q1–Q2; T7's re-freeze timing (handoff question 7); and the four pieces of work `TRIAGE.md` §3 recommends next.

## 11. T9 live probe 1 (2026-10-04, after the triage)

Run on the VM in `~/aew-review/t9` against the real 2.0.18 binary, with a `dcd43f1` checkout plus the T1 patch at `~/aew-review/dcd43f1` (the shared review venv is now installed from that checkout). Facts (details and the captured requests in `T9-live-probe-1-results.md`, `repro/t9/`):

- OpenCode 2.0.18 puts MCP servers behind **Code Mode** by default: the model request carries an `execute` JavaScript tool and a partial catalog in the instructions ("aew (12 tools, 5 shown)"); the server's tools are not function tools. `codemode: false` on the server entry (a key the pinned schema has) exposes them directly: 21 tools, 11,178 bytes for the twelve AEW tools. **The T1 branch now sets it** (second commit on `review/t1-typed-lead-surface`; `T1-typed-lead-surface.patch` regenerated; `tree/` back on `docs/restructure`).
- A permission `deny` removes a tool's schema from the model request, for built-ins and MCP tools alike. The invocation projection's `deny *` already removes `execute`, `question`, `skill`, the web tools and the whole Code Mode section from a run's request (4 tools, 8,370 bytes total).
- Code Mode exposes a built-in `browser` namespace (45 desktop browser tools) whenever `execute` is allowed; the Lead's `* ask` rule allows it. Two new questions for the designer are in the T1 note's §14.
- A failed MCP server (no bridge, no token) is silent: no error reaches the session, the catalog simply lacks the namespace.
- The built-in `openai` provider is redirected with `providers.openai.settings.baseURL` (2.0.18 spelling); requests go to `/v1/responses`.

Remaining from `TRIAGE.md` §3 item 1: the Codex app-server handshake probe (needs the Codex binary on the VM; not installed without the operator's say-so).

## 12. T9 live probe 2: the Codex app-server (2026-10-04, with the operator's permission to install)

Codex 0.160.0 is installed under `~/aew-review/codex/` on the VM only (release tarball plus its sigstore bundle; nothing on `PATH`, no sudo). Results in `T9-live-probe-2-results.md`; requests in `repro/t9/codex_request_C*.json`; the generated v2 protocol schema in `repro/t9/codex-app-server-protocol.v2.schemas.json` (the fixture candidate).

- The app-server handshake and thread lifecycle work over stdio; `mcpServerStatus/list` shows `aew lead mcp` connected with the twelve T1 tools, `enabled_tools` narrows the inventory, a failed server is reported with its error (the opposite of OpenCode's silence).
- MCP tools are **deferred** into Codex's `exec` runtime: no `aew` tool is a function tool in the model request on this pin, and none of the flags tried changed that. Sub-agent tools (`collaboration` namespace) were in every request, including with `multi_agent` disabled. A Codex adapter cannot yet promise the typed Lead surface as tools; `DynamicToolSpec` (experimental API) is the route to probe next.
- Tools travel inside an `additional_tools` developer input item of the Responses API request, not in `tools`; the base prompt is 19 KB of Codex's own instructions; a bundled `imagegen` system skill is advertised from a fresh private `CODEX_HOME`.

`TRIAGE.md` §3 item 1 is now complete for both harnesses. VM scratch (`~/.aew-test-tmp/review-*`) is clean; no probe process is left running.

## 13. T4 prototype: knowledge records in the manifest, on a review branch (2026-10-04)

After the designer approved ADR-0013 with terminology edits, the review built `review/t4-knowledge-manifest` in `tree/` (from `dcd43f1`; exported as `T4-knowledge-manifest.patch`; `tree/` left on `docs/restructure`). `T4-knowledge-manifest-prototype.md` lists the files, the five decisions the prototype made where the ADR left room, and how to run it. Facts a later session should not re-derive:

- The manifest, the chain, verification, the derived index and the ADR-0011 surface (`history show/list/links`, the audit) take the five knowledge kinds with only the schema enum and `ENTRY_KINDS` changed; `history.schema.json#/$defs/entry` gains an optional `version`.
- A knowledge commit (`aew knowledge case`) is one Lead transaction that stages the case, its initial disposition and the receipt through `History.write_record` and appends their entries via `ctx.entries`, which the archival finalizer appends in one `History.append`. It changes only `revision`, `counters`, `knowledge`, `cold`, `last_transition` (and the finalizer's own empty hot keys on a first append); `work`, `invocations`, `tokens` and `lead` are untouched (tested, rule 28).
- The index gained `about(subject, kinds)`, `versions`, `current` (the disposition fold) and an FTS5 table over knowledge record bodies with `search`; hits are authenticated at their positions, a planted row is dropped by an SQL kind filter rather than read as index disagreement, and text FTS5 rejects is searched as a phrase.
- A crash at `history.after_tail` inside a capture commit leaves the old or the new history and the next capture succeeds (the existing fault points cover knowledge records; no new ones).
- Not modelled: D9's service identity (the Lead commits), K2 `lesson` and K0 `reference` records beyond the enum, the K1 template matcher, pack-side rules, the dashboard projection.
- Two registries a new command family and a new hot key must join, found by the regression lane and not by the new tests: the DispatchDecision CLI enumeration (`tests/unit/test_dispatch_decision.py::NOT_DISPATCHING`, or the dispatch entrypoint registry) refuses an unclassified command; and three hand-rolled v1 fixtures (`tools/perf/control_plane.py`, `test_history_surface.py`, `test_archival.py`) downgrade `aew init`'s v2 output by popping `cold` only, so any v2-only key `init` writes breaks them until it is popped too. The v2-only key set is spelled out in the schema's v1 exclusion, in `init` and in those fixtures with no shared constant (`T4-knowledge-manifest-prototype.md` §3). `aew migrate` needed no change (D11).
- Lane evidence: 865 passed, 1 skipped, 3 fixture failures fixed and rerun green; ruff clean; pyright 0 errors on the changed `src/aew` modules. Commit `a9a9cd9`.

## 14. T7 citation test, run once over the living documents (2026-10-04)

`T7-citation-test-results.md`; probe `repro/t7/citation_probe.py`, outputs beside it. Read-only over `tree/` at `dcd43f1` and the live checkout at `56b85ad` (`impl/m4-b-containment`, which does not contain `dcd43f1`; the flat layout is mapped to the map's sets by basename). Facts a later session should not re-derive:

- 81 explicit contract citations of 39 sections in 28 living documents at `dcd43f1` (98 of 41 in 29 on the live branch, which still counts the ambiguity and M3 reports as living). 27 (33%) touch an indexed section: 18 of replaced sections (WC §7.4, §7.5, KC §26), 9 of pending ones.
- Check 2 with the sketch's naive rule: 13 flags, 12 of them citations that do not depend on the replaced text (other KC §26 cases, §7.4 inheritance, §7.5 for Classes 1–4, the amendment's own file). With a per-entry `topic` (Class 0 / eligibility for §7.4 and §7.5, "parent risk" for KC §26) and the amendment file exempt: one flag on both checkouts.
- That flag is a defect: `docs/guides/acceptance.md:33` (live: `docs/implementation/acceptance.md:33`), the AT-9 row, describes the frozen case ("keeps class 0, inherits the gate") while `test_parent_risk_policy_propagation` asserts the amended one (eligibility refused, `CLASS0_INHERITED_ELEVATED_OBLIGATION`, reclassification, gate still required). Fix the row; cite the amendment's §9.
- Check 3 (pending sections cited as settled) flagged 8 and 13 paragraphs, every one a valid citation of text still in force. Drop it; keep `pending` in the index as the re-freeze debt list.
- The index candidate in `T7-amendment-index.md` §4 needs a `topic` field per `replaces` entry; without it the test's precision on this corpus is 1 in 13, with it 1 in 1.
- Not read: the designer's untracked `docs/T7-amendment-index-v0.2.md` and sibling `T*`/`ADR-0013` copies in the live checkout.

## 15. T6 artifacts: the register entry and the ADR-0009 amendment text (2026-10-04)

`T6-register-entry-and-adr-0009-amendment-draft.md`. Written read-only against the live checkout (`impl/m4-b-containment` at `56b85ad`), whose M4-B amendment to ADR-0009 (2026-10-03) `dcd43f1` does not have. Facts a later session should not re-derive:

- The M4-B amendment documents a residual the T6 proxy closes for the provider key: the harness server's environment (provider key and `OPENCODE_PASSWORD`) is readable from the agent's shell via `/proc/<parent>/environ`; `tests/integration/test_opencode_adapter.py::test_residual_the_harness_servers_environment_is_readable_from_the_agents_shell` asserts it as it is. Under `proxy_only` the key is not in the server's environment at all; the password still is, so the residual narrows rather than closes.
- Live label code: `containment.label()` returns `{filesystem, process_ownership, network: "not_provided", mechanism}`; the policy schema's `containment` has `mode, writable, hide, trusted_git_drivers`; `checks.yaml` per-check fields are `configured, command, cwd, timeout_s, description`. The register's ids run F1–F20; the draft uses F21 as a placeholder for the review's F-F.
- The draft's meaning change: a contained Linux run with the host's network is `network: shared` from the amendment on; `not_provided` is reserved for platforms where AEW has not addressed the network (Windows). Old Linux records read as `shared`, none rewritten.
- Six decisions for the designer (default `proxy_only`; the Lead's TUI out of scope; checks default `network: none`; catalog seeding; read-as relabel; the register id), each with the review's recommendation.

## 16. D9 spike: the `knowledge_service` principal, on a review branch (2026-10-04)

The designer answered ADR-0013 question 1 (accept the closed non-Lead committer; own credential kind; only the runtime-enforced `knowledge.*` family; no Lead credential, no inherited Lead authority; survives handoff/takeover) and asked for a spike proving only that boundary. `T4-D9-service-identity-spike.md`; branch `review/t4-d9-service-identity` (`d9a9645`), exported as `T4-D9-service-identity.patch`; `tree/` left on `docs/restructure`. Facts a later session should not re-derive:

- The ADR-0005 architecture takes a fourth credential kind without changing form: `service`, scope `{service, family, issued_by}`, **no generation**. `_revoke_all_lead_credentials` revokes `lead` and `handoff_offer` only, so handoff and takeover leave a service credential alone by construction (no change to `lead_ops.py`); the new Lead revokes or rotates it with `aew service issue|revoke`.
- The closure is enforced in `ControlStore._commit` (`engine/closure.py`): for a service actor the store diffs the committed state against the one to write and refuses any key, counter, record path or op outside the family (`TRANSACTION_CLOSURE`), before validation and before any disk write. Tested both through `service_txn` and by committing straight through `store.session()` with a service actor.
- A service transaction runs with `TxnContext.archival=False`: the archival finalizer appends the operation's own entries and archives nothing, ends no credential, prunes nothing. Without this, any knowledge commit with finished units pending would move work to the cold store under a service actor.
- `aew knowledge case|dispose` route by credential kind (`Kernel.actor_txn`); `AEW_SERVICE_TOKEN` is the explicit-credential path; the Lead broker refuses `service issue`; `agentenv.build` drops the variable; the secret is in no file or output.
- Evidence: Windows 7 passed + 1 pty skip; Rocky 8 VM 8 passed (takeover through a pty); lane: 894 passed, 3 skipped (two pty cases, xdist) in 21m45s on Windows.
- Open for the designer (spike §5): expiry for service credentials; where the capture service's process keeps its credential (M6b).

## 17. T5 probe: the codebase map from Git objects (2026-10-04)

`T5-codebase-map-probe-results.md`; probe `repro/t5/codebase_map_probe.py`, outputs and two generated records beside it. Read-only on `tree/` @ dcd43f1, the live repository @ dcd43f1 and @ 56b85ad, and `security-platform-toolchain` @ 3bf796b. Facts a later session should not re-derive:

- Cost: about 0.1 s and 3.5 KB for every §2 section but the import graph; the graph is 85–90% of time and bytes (0.5–0.6 s, 25 KB on AEW's 212–217 modules). Deterministic across repeats; byte-identical for one commit from two checkouts.
- `git ls-files` lists the checkout's index, not the commit: the first run gave 809 files in `tree/` and 930 in the live checkout for the same commit. The generator must use `git ls-tree -r --name-only --full-tree <commit>`.
- Freshness: the no-imports map depends on the tree listing plus two or three configuration files, not on every file's content. On the live repository 21 of the last 30 `main` commits changed contents only; a listing-plus-config rule keeps the map CURRENT through them. With imports on, modified `.py` files stale it (40 of 73 content-only changes between dcd43f1 and 56b85ad).
- `ignored_but_present` cannot be computed from objects (it describes a working tree).
- The fixed role table labels 2 of 7 AEW and 8 of 13 SPT top-level directories `unknown`: honest, and the architecture map's job to explain.
- Not read: the designer's untracked `docs/T5-project-maps-v0.3.md`.

## 18. The semantic-map brief (2026-10-04, afternoon): S1–S7

The designer's second brief (after T4/T6/T7/D9/T5 closed) asked for a real C/C++ investigation, the extension contract alongside it, the agent-facing surface, incremental freshness, the architecture-map bridge, a query-routing design using a security-research platform as the prior, and a large-repository benchmark. All seven are delivered as notes above. Facts a later session should not re-derive:

- **VM toolchain (installed by the operator 2026-10-04):** `clang clang-tools-extra llvm llvm-devel python3-clang cmake make gcc gcc-c++ glibc-devel`; **no `ninja`, no `bear`, no `clangd-indexer`**. `python3-clang` targets the system Python 3.6; the review venv has the `libclang` 18 wheel (`pip install libclang`), which parses with `-resource-dir $(clang -print-resource-dir)`. Targets under `~/aew-review/sem`: zlib 1.3.1 (`zlib/build`, 34 TUs) and curl 8.11.1 without TLS/compression (`curl/build`, 1,379 TUs; `cc-lib.json` the 434 library entries), both Debug; `zlib/build-cov` with coverage flags. Scripts and outputs beside them; the extraction JSONs (134 MB for curl lib) stay on the VM, the oracle JSONs and summaries are in `repro/sem/`.
- **The boundary, measured:** S1 §3. The three probe iterations each found a real thing: parenthesized callees (`referenced` is None), asm-label renames (`mangled_name`), dispatch tables in initializers. Any extractor must handle all three.
- **Per-TU dumps are 100× redundant** (393,968 symbol records, 3,866 distinct USRs); the artifact is a deduplicated symbol table or it is nothing.
- **Fan-out:** `clang-scan-deps` 2 ms/TU; curl lib: 158 project headers, median fan-out 21, six reach all 434, 116 of 198 system headers reach all.
- **Answer sizes** (`repro/sem/cxx_query.sample.out.txt`): the radius-2 cliff is the budget fact S3 and S6 rest on.
- **The approved doc set** is on `origin/docs/ingest-outbox-knowledge-eval-network-harness` (28 commits on dcd43f1; ADR-0012/0013 adopted; recall/context-routing design v0.3; requirements ledger; `main` does not yet contain the docs restructure). F22 is the project-maps register row; ARR-70 says "semantic map separate". The designer's `T5-project-maps-v0.3.md` and `T7-amendment-index-v0.2.md` were not read.
- Synthetic benchmark scratch `~/.aew-test-tmp/review-synth` removed; `~/aew-review/sem` is 610 MB and can be deleted when the thread closes.

## 19. Third brief, started (2026-10-04, evening; cut off by the session's usage limit): project understanding, Project Profile, Requirement Impact Analysis

The designer's brief (Parts A–E, 15 questions, 9 deliverables) is pasted in the conversation of session 889ae5c3; no note is written yet. Groundwork established, so the next session does not re-derive it:

- **Ground truth for a deterministic impact-analysis probe exists on the live branches**, each a requirement with its real change surface: (1) `9102b9b` "Integration recovery: a later operator commit never strands a publish" (base `ce794fb`; 4 src files + 1 regression test); (2) M4-C "mutating concurrency above 1" (`e91ab4f` + `c2cf8be` + `a98556e`, base `ce794fb`; 3 src + 7 test files); (3) M4-A "one dispatch predicate" (`a149563` + `6746033`, base `4cc8bd8`; ~45 src/test files). Plan: compute the affected surface from requirement seed terms over the base tree (Python `ast` symbol/call index, tests, invariants, schemas, ADR mentions), score recall and false-positive expansion against these; probe not yet written (`repro/ria/`).
- **The plan-assurance design v0.4 already owns much of Part C:** first-pass acceptance inputs (governing contracts, parent invariants, current evidence), load-bearing premises with discriminating probes (§8), dependency-sensitive invalidation, the "stale project map" adversarial task family, the investigator as the owner of bounded evidence. Impact analysis should be positioned as the *deterministic supplier* of those inputs and candidate premises, not a parallel artifact. This is the main contradiction with the brief's layered hypothesis to write up.
- **Existing vocabulary to reuse, not reinvent:** WC §16.15 "project profiles may declare machine-readable guardrails" (ownership/directory boundaries, dependency directions, layering, generated-file policy, contract locations); WC §11.2 and §22 "build/test impact analysis" (targets, tests, cheap-first order); KC §8.1–§8.5 (overview, architecture map, codebase map, ownership map, glossary; "clearly identify summary versus authoritative source"); the hierarchy design §12 "goal change impact analysis" checklist and its explicit impact classification; ADR-0008 discovery records (`facts[{statement, evidence[]}]`, `observed_paths`, source-bound freshness); `engine/freshness.py` (CURRENT/STALE/UNKNOWN over declared paths).
- Candidate answers forming: the Profile is a small set of structured records (stack/build/test facts deterministic from the T5 map and the build; architecture and ownership as evidence-bound synthesis records with per-claim `observed_paths` freshness), queried on demand, projected for humans; "concerns" are requirement-relative, computed at Story scope and inherited by Tickets; Epic analysis is subsystem-level, Story analysis is file/symbol/contract-level; the deterministic part is seed → symbols → radius-1 → tests/invariants/schemas/ADRs; the model part is risk statements and premise selection; an investigator is launched when a load-bearing premise has no current evidence.

## 20. Third brief delivered; the C++ contract check (2026-10-05)

- `S8-project-understanding-profile-and-impact-analysis.md` answers the brief's 15 questions and 9 deliverables. Probe facts a later session should not re-derive: ground truth = `9102b9b` (integration recovery, 4 existing src files + 1 created test), M4-C `e91ab4f`+`c2cf8be`+`a98556e` (3 src + 4 tests), M4-A `a149563`+`6746033` (24 existing src + 5 tests, 10 created files); index of the base trees: 169–185 Python files, 2,400–2,600 symbols; the deterministic surface takes about 2 s. The constraints pass (oracle rules, schema keys, ADR mentions, error codes) surfaced the serial-cap rule and the integration rules without a model.
- `S1b-cxx-plus-plus-contract-check.md`: fmt on the VM (`~/aew-review/sem/fmt`, Debug, tests on). libclang's AST has the template, codegen has the instances: tens of thousands of weak symbols with no AST definition; calls on dependent names inside template bodies have no referent until instantiation; implicitly-defined special members are emitted without a definition cursor; virtual calls are indirect in codegen with a known static target. The probes classify all of these now (`template`, `dependent`, `virtual` edge kinds; `template_instantiation`, `constructor_or_destructor` symbol classes). Per-TU cost on template-heavy TUs is 1.3 s parse + 4 s walk.
- The designer's consolidation path stands: T5 structural probe + S1–S7 + C++ probe → T5 v0.4 → contract freeze. S8 §8 lists the four hooks T5 v0.4 needs (ls-tree, test index, public-surface counts, constraint locator index) and keeps the Profile/impact work out of it.

## 21. Program state after the designer's 2026-10-05 decisions

- **D9:** architecture proven on the spike branch; next is approving and amending ADR-0005/ADR-0009/ADR-0013 with the text in `T4-D9-service-identity-spike.md` §4; the capture service itself is a later implementation.
- **Semantic maps:** research capped. Consolidation = T5 v0.4 (structural: `ls-tree`, listing-plus-config freshness; nothing semantic required) + the semantic-extension contract freeze (S2 contract + S1b additions: `instances[]`, `dependent | virtual | overrides`, mandatory toolchain identity, `source: codegen`). Sibling derived indexes (test index, public-surface counts, constraint locator index) are composed when their inputs exist and are not fields of the structural record (S8 §8, corrected).
- **S8:** stable project understanding through existing KC §8 machinery as evidence-bound records; a new deterministic impact surface (`aew impact`, one implementation, Lead command + Plan Assurance consumer; radius 1 default) feeding Plan Assurance's first-pass artefact; Epic passes on directory roles with declared reduced coverage until `components[]` exist; investigator triggers advisory during evaluation; a 20–30 case stratified real-change corpus decides promotion (S8 §10).
- Nothing in this review is left open for research; what remains is the implementer's consolidation and the designer's ADR amendments.

