# Triage of the remaining review threads (T2, T4–T10)

- **Written:** 2026-10-04, in answer to the designer's addendum (`HANDOFF-addendum-designer-2026-10-04.md`). Revised at the end of the same session with what the probes and research found; the "status" column says what this session delivered.
- **Basis:** the handoff (`HANDOFF.md` §3–§5, §8–§9), the M4 phase plan (`m4-ambiguity-report.md` §5), the F15 ordering decision (two-surfaces note §14), the register (`future-work.md`), and the evidence produced in this directory.
- **Discipline:** classifications are recommendations to the design authority and operator. Nothing here reopens T1, ADR-0011, ADR-0012 or `DispatchDecision`.

## 1. Classification and order

| # | Thread | Class | Rank | Status after this session |
|---|---|---|---|---|
| T9 | Harness-native integration strategy | **TARGETED RESEARCH / LIVE PROBE** | 1 | Research note delivered (`T9-harness-native-integration.md`): matrix, profiles, seams, support target; live probes listed, two run |
| T6 | Network containment | **TARGETED RESEARCH / LIVE PROBE** | 2 | Probes run on the real Rocky 8.10 kernel; note delivered (`T6-network-containment.md`) with the egress design candidate and the label change; **artifacts drafted** (`T6-register-entry-and-adr-0009-amendment-draft.md`): register row and ADR-0009 amendment text, against the live M4-B amendment |
| T4 | Knowledge storage placement | **BOUNDED DESIGN** (done) | 3 | ADR draft delivered (`ADR-0013-knowledge-storage-placement-draft.md`) with a probe; **approved with terminology edits**; prototype branch `review/t4-knowledge-manifest` built afterwards (`T4-knowledge-manifest-prototype.md`); **Q1 answered, D9 spike built** (`T4-D9-service-identity-spike.md`): the closed non-Lead committer holds on the existing credential architecture |
| T7 | Re-freeze and amendment index | **GOVERNANCE CLEANUP** | 4 | Index and test sketch delivered (`T7-amendment-index.md`); **test run once** (`T7-citation-test-results.md`): refined rule flags one real defect (acceptance.md AT-9), check 3 dropped; build it as the documentation Ticket |
| T2 | Evaluation component | **BOUNDED DESIGN** | 5 | Plan delivered (`T2-evaluation-component-plan.md`); the external comparator is left as a verification item |
| T10 | Installation, bootstrap, integration UX | **TARGETED RESEARCH**, design bounded to F18's shape | 6 | Research and design note delivered (`T10-install-bootstrap-ux.md`) |
| T5 | Project maps | **BOUNDED DESIGN** | 7 | Design note delivered (`T5-project-maps.md`), smaller than the handoff asked: generator and freshness, not pack budgets; **generator probed** (`T5-codebase-map-probe-results.md`): cheap and reproducible from Git objects, with two corrections (`ls-tree`, section-scoped freshness) |
| T8 | Remote integration target | **WAIT FOR DEPENDENCY** (designer question 8) | 8 | Sketch only (`T8-remote-integration-target.md`), stopping at the adapter interface |

**The next two to four pieces of work** (§3) are: finish T9's two live probes against OpenCode 2.0.18 and the current Codex app-server; take T6's egress proxy from probe to an F-F register entry and an ADR-0009 label amendment; decide T4's question 1 (a non-Lead committer) because M6b cannot be planned without it; and run T7's index test once, in the live repository, to see how many citations it catches.

## 2. Thread by thread

Each entry answers the addendum's six questions.

### T9. Harness-native integration strategy — TARGETED RESEARCH / LIVE PROBE, rank 1

- **Why now.** M4-E (stage commands) and the T1 transport both sit on the OpenCode adapter; a Codex adapter is register item D5 and conformance §4 already sketches one. Every week the two products move: the pinned 2.0.18 OpenAPI already differs from OpenCode's public documentation (HANDOFF §9), and Codex's documentation moved domains and retired `codex mcp-server` in favour of `app-server` during this review. Getting the capability boundary wrong means a second authority path (native approvals, native subagents, native session resume) creeping in through an adapter; that is architectural rework.
- **Exact uncertainty.** Which native capabilities exist *in the versions AEW will pin*, which are stable, and whether the planned capability registry (F12, F13) can represent them without inventing one entry per harness quirk.
- **Expected artifact.** The capability matrix, the per-harness MUST/SHOULD/OPTIONAL/DO-NOT-USE/PROBE profile, named adapter seams, and the first support target. Delivered.
- **Blocker it clears.** The M4-E transport choice for roles (the `aew-run` server, T1 §6), the Codex adapter's scope, and the F13 registry's first entries.
- **Cheapest way.** Primary documentation plus two live probes: tool filtering at the request level on 2.0.18 (does `tools: {"x*": false}` remove schemas from the model request?) and the Codex app-server handshake with `dynamicTools`. Design prose cannot answer either.
- **Stop condition.** The matrix has an evidence column for every row, the two probes are run, and the support target is one page.

### T6. Network containment — TARGETED RESEARCH / LIVE PROBE, rank 2

- **Why now.** The VM is up, the M4-B layout is built with `network: not_provided`, and internal alpha's security review will ask about egress first (REVIEW G5). The proxy design moves the provider key out of the sandbox, which also closes the environ-read lead. A probe is worth more than another page: whether Bun honours proxy variables and whether the supervisor can still reach a server behind `--unshare-net` are facts, not design.
- **Exact uncertainty.** Does `opencode-cli serve` work with no network; what it fetches at startup; whether its runtime honours `HTTPS_PROXY`; how the supervisor reaches the private server across the namespace; whether slirp4netns is an alternative.
- **Expected artifact.** Probe results and a design candidate (the egress proxy, the in-sandbox forwarder, the label vocabulary), plus the register entry text. Delivered.
- **Blocker it clears.** F-F's register row; the ADR-0009 label amendment; where the provider key lives in the F18 bootstrap (T10).
- **Cheapest way.** The two probe scripts in `repro/t6/`, one hour on the VM.
- **Stop condition.** Every §6 probe of the containment research has a network sibling with a result; the design candidate names the one engine change (the forwarder) and the one adapter change (proxy environment).

### T4. Knowledge storage placement — BOUNDED DESIGN, rank 3 (done)

- **Why now.** M6b cannot be planned without it; the outbox draft's question 6 and the knowledge drafts' §17 and §26 wait on it. Low external uncertainty: the manifest exists and the probe showed it takes the new kinds unchanged.
- **Exact uncertainty remaining.** One authority question (a non-Lead committer, ADR-0013 Q1) and four smaller designer choices (Q2–Q5).
- **Expected artifact.** The ADR draft. Delivered.
- **Blocker it clears.** M6b's first increment (arm B over FTS), the capture worker's cursor, the `/knowledge` dashboard projection.
- **Cheapest way.** Done: in-memory schema widening against the frozen tree, 6,006 entries.
- **Stop condition.** The designer answers Q1; the rest can be settled in the M6b plan.

### T7. Re-freeze and amendment index — GOVERNANCE CLEANUP, rank 4

- **Why now.** Cheap, and it removes a class of silent error: a guide or ADR citing WC §7.4 or KC §26 as frozen text when an amendment replaced it. The map does this by hand today (REVIEW G6). It also tells the designer how large the v0.8/v0.5 re-freeze is.
- **Exact uncertainty.** None external. The question is coverage: which sections are amended, by which documents, and whether a test can be written that does not need to parse prose.
- **Expected artifact.** The machine-readable index beside `spec-pin.yaml`, the list of amended sections, and a test sketch. Delivered.
- **Blocker it clears.** The re-freeze's scope (designer question 7).
- **Cheapest way.** Grep the living documents for `WC §` and `KC §` citations (done: 36 distinct sections cited) and cross them with the amendments' "Amends" lines.
- **Stop condition.** The index lists every amendment on the map and the test passes on `dcd43f1` with the expected failures named.

### T2. Evaluation component — BOUNDED DESIGN, rank 5

- **Why now, and why not deeper.** F19 is decided (one program) and every post-M3 question routes through it (REVIEW G1), so the shape matters. But it is a plan for code that does not exist, with one external dependency (the comparator), and the first consumer (M4-H's preregistered dogfood) is several phases away. Deep design now would be prose ahead of evidence; what is needed is the package layout, the run-record schema and the preregistration record, so that M4-H's experiment can be written against them.
- **Exact uncertainty.** The external comparator (a gateway-side model and its pinned configuration), the hidden-evaluator channel on an air-gapped host, and how `aew-private/eval` and the repository split the corpus.
- **Expected artifact.** A plan: layout, `aew/eval-run/v1`, preregistration record, hidden channel, incident corpus list, comparator verification item. Delivered.
- **Blocker it clears.** M4-H's preregistration; F17 phase 1; the K1 template replay (T4/M6b).
- **Cheapest way.** Generalise `eval/m3/dogfood/dogfood.py`'s record and driver; the schema first, the runner later.
- **Stop condition.** The schema validates the M3 `results.jsonl` records unchanged (backward compatible) and one new preregistration record exists for M4-H.

### T10. Installation, bootstrap and integration UX — TARGETED RESEARCH, design bounded, rank 6

- **Why now, and why bounded.** F18 is unscheduled and waits on Q12 (hosting). But the air-gap deployment is a hard constraint (Rocky 8, no hidden fetches), the T6 and T9 results change what `aew doctor` must check (proxy, catalog seeding, protocol shape), and the configuration-ownership model decides where the T1 projection and the T6 proxy configuration live. The research is cheap; the design must stop at the shape F18 will fill, not an installer.
- **Exact uncertainty.** Which ownership model the harnesses allow (OpenCode merges config layers and takes `OPENCODE_CONFIG_CONTENT`; Codex layers `config.toml` with `--config` overrides and `requirements.toml`), and what a complete offline bundle must contain (the model catalog is now known to be a network fetch).
- **Expected artifact.** The survey, the workflow, the ownership model, two profiles, upgrade and rollback, failure UX, the ownership split, non-goals. Delivered.
- **Blocker it clears.** F18's milestone assignment after Q12; the doctor checks for M4-B and F-F.
- **Cheapest way.** Documentation survey plus the facts T6 and T9 produced; no new probes.
- **Stop condition.** Every list in the addendum's deliverable has one paragraph, and the non-goals are explicit.

### T5. Project maps — BOUNDED DESIGN, rank 7

- **Why now, and why small.** The gap is real (REVIEW G3: reviewers see diffs with no architecture context; the Lead guessed seven globs) and the knowledge drafts classify the map as K0 material, so T4 fixes where it would be stored. But the pack-budget half of the question depends on the recall draft's budgeting (K-arm evaluation) and on M6b. The deterministic generator and `observed_paths` freshness are decidable now; budgets are not.
- **Exact uncertainty.** Whether a deterministic codebase map is worth its context cost before any measurement; what the first generator should emit.
- **Expected artifact.** The generator's output shape, freshness, `aew map` commands, and where it sits in T4's storage. Delivered, with pack sections and budgets listed as evaluation questions.
- **Blocker it clears.** The `codebase_map` knowledge entry stops being `null` at `aew init`.
- **Cheapest way.** Reuse `knowledge/discovery.py` and the freshness code for discovery records.
- **Stop condition.** One generator, one freshness rule, one command group, no pack change.

### T8. Remote integration target — WAIT FOR DEPENDENCY, rank 8

- **Why not now.** Designer question 8 (in scope before internal alpha?) is open, M4-D is still designing the local queue and lease, and a remote target changes `DONE` semantics (observed merge) which M4-D's reconciliation must accommodate. Designing the adapter before M4-D's records exist would be rework bait.
- **Exact uncertainty.** Whether a remote target is wanted at all before alpha; which provider first.
- **Expected artifact.** A sketch of `integration.target` and the provider adapter interface, stopping before reconcile. Delivered as a sketch.
- **Blocker it clears.** None until question 8 is answered.
- **Cheapest way.** Wait; then one ADR-0004 amendment.
- **Stop condition.** The designer answers question 8.

## 3. Recommended next work (two to four pieces)

1. **T9 live probes** (half a day on the VM): request-level tool filtering on OpenCode 2.0.18 and the Codex app-server `initialize`/`thread/start` handshake with `dynamicTools`, both recorded as fixtures the capability probe can check. They decide the role transport for M4-E and the Codex adapter's first scope. **Update, later the same day:** the OpenCode probe is done (`T9-live-probe-1-results.md`): `deny` removes schemas from the request; 2.0.18's default Code Mode hid the T1 tools until `codemode: false` was set (fixed on the T1 branch); a built-in 45-tool `browser` namespace is reachable through `execute`. The Codex probe is also done (`T9-live-probe-2-results.md`): the app-server handshake and MCP spawn work and failures are loud, but on 0.160.0 MCP tools are deferred into the `exec` runtime and sub-agent tools are present regardless of flags; a Codex adapter cannot yet promise the typed surface as tools.
2. **T6 into the register** (a day): F-F's row, the ADR-0009 label amendment (`network: proxy_only | shared | not_provided`), the forwarder in the supervisor's layout, and the proxy in the adapter's environment, behind the existing fail-closed self-test. The probes show every piece works on the real kernel. **Done 2026-10-04** (`T6-register-entry-and-adr-0009-amendment-draft.md`): the register row and the amendment text exist as drafts; six decisions remain for the designer, the Ticket is Class 2.
3. **T4 question 1** (a designer decision, no engineering): whether the capture service identity may commit a closed `knowledge.*` transaction family. M6b's plan depends on it; nothing else in ADR-0013 does. **Answered 2026-10-04** (accept the closed non-Lead committer); the D9 spike (`T4-D9-service-identity-spike.md`) proves the boundary with 8 tests; M6b can build on it.
4. **T7's test in the live repository** (an hour): run the amendment-index test once against `main` to see which citations it catches, then decide whether the re-freeze is a documentation task or a contract revision. **Done 2026-10-04** (`T7-citation-test-results.md`): a third of citations touch the index; the refined rule catches one real defect and nothing else; the re-freeze stays a documentation task plus the unwritten Ticket-revision amendment.

Not recommended now: a Codex adapter implementation (T9's support target says what it would have to pass first), the F19 runner (T2's schema first), the map generator (T5's generator waits on a measured need), and anything under T8.

## 4. The semantic-map brief (2026-10-04, afternoon)

Delivered, in the designer's order: S1 C/C++ investigation (live, measured against the compiler's own output), S2–S5 contract/surface/freshness/bridge (one note), S6 query routing (Revelations as prior), S7 large-repo benchmark. Next, if the designer wants more: a C++ run of S1 (templates and instantiations are the unmeasured fourth category); a C++ or Rust extractor to replace the Python walk if 50k-TU repositories are in scope soon; the S6 evaluation set generated from the curl extraction (A/B/D classes need no labels); and the designer's five S2–S5 decisions.

## 5. Third brief and the C++ check (2026-10-05)

S8 delivered (profile and impact analysis as record families and plan-assurance inputs, not new layers; the deterministic surface probed). The C++ run of S1 delivered as S1b. The research thread can stop here, as the designer proposed, and move to consolidation: T5 v0.4 with the four S8 §8 hooks, then the semantic-extension contract freeze with the S1b additions (instances, `dependent`/`virtual` edges, the IR-based extractor identity for C++ edges).

Designer decisions 2026-10-05 recorded in S8 §10 and HANDOFF §21: S8's five questions settled; T5 v0.4 keeps the structural record independent of semantic data, with the test index, public-surface counts and constraint locator index as sibling derived indexes. Research threads closed; consolidation is the implementer's.

