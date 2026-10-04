# AEW architecture review, ground up

> **Archived record (2026-10-04).** Its disposition is the proposed [architecture review response](../../design/proposals/architecture-review-response-2026-10-04.md); every item is tracked in the [requirements ledger](../../design/requirements-ledger.yaml) (ARR, ARV). I1 and I2 were fixed in M4-B (#36) before this record was published. Sanitized for the public repository: reviewer-local paths removed.

- **Basis:** branch `docs/restructure` at `dcd43f1` ("Docs: a map and a structure by status"), in a separate clone; plus the three M6 knowledge-system drafts as they stood before their later revisions (capture/admission v0.3, recall/routing v0.2, shared semantics v0.3; then untracked, now in `docs/design/proposals/` as v0.4, v0.3 and v0.4).
- **What was read:** everything `docs/README.md` lists as governing or living (the frozen set, both contract amendments, the decisions record, plan assurance v0.4, the F15 idea note, ADR-0001 to ADR-0011, `implementation-status.md`, `future-work.md`, the M4 report, the testing strategy, harness conformance), every proposal and research note, the skills package, the four guides, and the archive records that carry evidence (the M3 dogfood report, evidence synthesis, both M3 audits, the M3 review response, the Ticket-revision review, the ADR-0011 brief and P3 results). Code was sampled where the documents point: `knowledge/context.py`, `harness/opencode/projection.py`, `engine/{dispatch,reasons,primitives}.py`, `knowledge/manifest.py`, the role archetypes and cards, the CLI command table, `pyproject.toml`, CI. Nothing was run; this is a design review, not a reproduction.
- **What was not read:** private notes, and the research basis the knowledge drafts cite, which was not in the checkout at the time (since added as `docs/research/aew-knowledge-capture-admission-and-agent-usefulness-v0.1.md`).
- **Confidence legend:** **H** = follows from the documents' own evidence or from reading the code; **M** = a judgment about design consequences I did not test; **L** = depends on facts outside the repository (tool behaviour after my knowledge cutoff, the organisation's gateway, future measurements).
- **How to read this.** §1 is where the architecture stands. §2 is the ranked list of gaps and risks in the architecture as designed. §3 is improvements to mechanisms that exist. §4 is upgrades: tech stack, MCP servers, skills. §5 is whole features. §6 is the assessment of the three knowledge drafts. §7 is what looks sound and should be left alone. §8 is a sequencing proposal. §9 is process notes. The brief's "go wild" licence is used in §4 and §5; §2 stays conservative.

---

## 1. Where the architecture stands

AEW is, as built, a **control plane with an unusually strong authority story and a thin knowledge story**.

What is proven (by tests, adversarial walks, crash matrices, an invariant oracle, independent reviews and two dogfoods):

- **Authority and custody.** One commit point with a checksum trailer and redo staging (ADR-0001); credential verifiers only, generation fencing, operator-at-terminal takeover (ADR-0005); the run supervisor and Lead broker holding credentials behind a JSON-only, three-operation bridge (ADR-0009). No credential reached any file in 68 dogfood runs. This is the part of AEW that has survived every attack the reviews mounted.
- **Legality has one source.** `DispatchDecision` over a declared entrypoint registry, enforced by a transaction finalizer that refuses any commit creating an invocation or run without an admitting decision (M4-A). Reason codes, failure classes and primitive declarations are registries, not prose.
- **Evidence binds to what it evaluated.** Fingerprints synthesized in a throwaway index (ADR-0002), check results bound to their definition digest, reports accepted only for the plan, attempt and candidate they were produced for (ADR-0004 R1). Staleness is computed, never written.
- **History independence.** Hot state tracks open work (H1 1.05x from 250 to 3,000 completed; history 7.6% of hot state), with a hash-chained, audited, selectively loadable cold store (ADR-0011).
- **Containment on Linux.** Bubblewrap with a PID namespace, private git object store, launch self-test, truthful labels (M4-B). My area-1 review found one major hole (operator-declared writable roots are not validated), which is a fix, not a redesign.
- **A harness boundary that a second adapter could satisfy**, with a conformance suite written once and driven by three drivers.

What the evidence says about value (M3 dogfood, `m3-evidence-synthesis.md`):

| Claim | Evidence |
|---|---|
| Durability | Lead harness destroyed mid-Ticket, context rebuilt from `.aew/` alone: 3 of 3 |
| Independent review catches defects | 19 of 19 first reviews caught the seeded defect |
| Custody | 0 credentials in files, 68 runs |
| Quality over a plain agent | **Not shown**: plain OpenCode 20 of 20; AEW 24 of 26; the tasks hit a ceiling |
| Cost | **About 7x** plain OpenCode in money and time; the Lead is about 40% of it, and that is choreography (about 20 workflow commands a session), not waiting |
| Harm | Once: T4, a goal met by editing its own inputs; every gate passed it |

What is designed but not built, in order of how often the documents gate other work on it: the evaluation program (F19, Q7), plan assurance beyond M4-A (F14), stage commands (F15), Ticket revisions (F4/F5), the integration queue (M4-D), the capability registry and skills (F12/F13/D3, M6), the knowledge system (the three drafts, M6), Lead and operator interaction (F8), live coordination (F9), the scheduler (M5), hosting and bootstrap (Q12/F18).

The shape of the risk follows from that table. The control plane is ahead of the evidence that it improves engineering outcomes, and almost every open design decision is waiting on an evaluation capability that is itself only designed. §2 starts there.

---

## 2. Gaps and risks in the architecture as designed

Ranked by how much of the roadmap depends on them. Each entry: the gap, the evidence, why it matters, what to do, and where it lands.

### G1. Evaluation is the critical path and is not yet a component (H)

**Gap.** F19 ("one evaluation program": one fixture format, runner, run-record schema, hidden-evaluator mechanism, metrics collector) is a register entry. What exists is `eval/m3/dogfood/dogfood.py`, a driver written for one experiment, with its hidden tests in `hidden.py` and a hand-written rubric. Every consequential open question routes through evaluation: the F14 class floors ("evaluation hypotheses"), Class 0 calibration (sampled audit), F17 (phase 1 baseline first), model routing (D5), skill adoption (the whole `docs/skills` package), K2 lesson admission (the knowledge drafts' phase 2), R2 model-diverse review (WC §22), and Q7 itself.

**Why it matters.** The M3 dogfood could not show a quality benefit because its tasks saturated. The documents know this (§11 of the report, Q7). Until there is a corpus where a single session fails or regresses, AEW cannot demonstrate the thing it exists for, and each design decision above is made on hypothesis. The governance is honest about it; the architecture does not yet give it a home.

**Recommendation.**
1. Promote F19 to a first-class component with the same engineering treatment as the engine: a `src/aew/eval/` package (or a sibling repository under the same CI), a versioned run-record schema (`aew/eval-run/v1`), a preregistration record pinned by hash before any paid run (the rubric practice, made mechanical), a hidden-evaluator channel that the worker's reach cannot touch (the scratch rule from F2 applies), and a metrics collector that reads the instrumented command log, the run records' usage, and the hidden-test verdicts.
2. Seed the corpus from AEW's own incidents, where the ground truth is known and the source material is durable: T4 (acceptance-input mutation), the §6.6 scope case, the malformed-goal case (T1 run 1), the R1 shallow-finding pair (T-0001/T-0003), the SPT headless premise, the subagent explosion (Incident A). The knowledge drafts and F17 name the same list; one corpus serves all three programs.
3. Add an **external comparator**, so that the ceiling problem cannot recur unnoticed: a slice of a public agentic benchmark with known per-task difficulty (SWE-bench Verified or a successor; Terminal-Bench-style tasks for the shell-heavy roles), run both plain and under AEW, at a fixed model. **L** on which benchmark fits the organisation's gateway and air gap; the point is to stop authoring every task in-house.
4. Make "replay a recorded project to revision N" a supported operation (see F-C in §5), because the T4 fixture is exactly that, and every future incident will want the same.

**Lands:** before M4-H's dogfood, which the M4 report already says should use F19's format "where it exists". It does not exist yet.

### G2. The Lead's interface is a shell, and the shell is where the cost and a whole defect class live (H)

**Gap.** The Lead drives AEW by typing `aew` commands into a harness shell: `--expect-rev N` on every mutation, free text through quoted heredocs and `--fields -`, results read back as text, waits in 110-second slices. The dogfood measured the consequence: a median of 20 workflow commands and 34 model steps per session, 261k cached tokens re-read, 51 refused commands of 887 (`ILLEGAL_TRANSITION` 32, argparse usage 8, `USAGE` 7). The ingress hardening (B1 `--fields`, I5 YAML pitfalls, M3-D2 byte-order marks, PowerShell here-strings) is all work spent making a shell carry data it should never have carried.

**Why it matters.** F15 (stage commands) attacks the step count and is right to. But stage commands delivered as more CLI commands keep every property that produces the refusals: untyped arguments, text results, a shell between the model and the engine. With M4's parallel runs, the spike already predicts more `STALE_REVISION` refusals (fact 2).

**Recommendation.** Give the Lead a **typed tool surface**: an MCP server over the Engine API (WC §15.6 and F12 already allow "an optional MCP adapter"; invariant 21 requires it to call the same engine, which it would). Concretely:
- The Lead broker already holds the Lead credential and relays `lead.cli {argv}`. Add a second relay operation, or make the broker itself speak MCP over stdio to the harness, exposing the F15 stage commands as tools (`ticket.draft`, `ticket.start`, `ticket.request_review`, …), `dispatch.explain`, `status`, `resume`, `harness.wait_any`, plus one escape hatch `aew.cli(argv)` for the primitive surface. Arguments are JSON; goals, scopes and reasons never meet a shell. Results are structured (`completed_steps`, `revision`, `runs`, `decisions_required`): the `ActionProjection` of the F15 note, which the TUI, the dashboard and the scheduler also consume.
- For role runs, the bridge's three operations (`whoami`, `check.run`, `submit`) become three tools served by a thin MCP client inside the sandbox that forwards to the supervisor's bridge, exactly as the `aew` CLI client does today. Custody is unchanged: the credential stays in the supervisor.
- `--expect-rev` stays a CAS, but the server can retry `MECHANICAL` primitives on `STALE_REVISION` after re-reading, which the F15 note already permits ("re-read and retry only where their guards allow it"). Judgment-bearing primitives never retry.
- Use the harness's deferred-tool or tool-search facility where the pinned release has one, so that about seventy subcommands do not sit in every prompt (the research's own warning, S24, S37, S39). **L** on which OpenCode release exposes what.

**Expected effect (M).** Most of the refusal taxonomy disappears (a typed tool cannot be called with the wrong option), the ingress defects cannot recur, every mutation returns its next action so the status reads between steps go, and `harness wait` becomes a blocking tool call rather than a model step per slice. This is the one change that attacks the 40% directly rather than by halving it.

**Lands:** as the implementation of the F15 stage surface (M4-E), with the broker and bridge changes in M4-D alongside wait-any. The knowledge drafts also assume an MCP or CLI knowledge capability (`knowledge.search/get/related/evidence/explain_selection`); building the transport once for the Lead gives it a home.

### G3. The Knowledge Contract's project-knowledge classes are specified and not implemented (H)

**Gap.** `aew init` writes a manifest whose `architecture_map`, `codebase_map`, `ownership_map` and `glossary` are `null`, and a `PROJECT.md` of `UNKNOWN` fields. Nothing generates them, nothing tracks their freshness (KC §13's `CURRENT/STALE/UNKNOWN` exists only for discovery records and plan proposals), and no context pack carries any of them: `knowledge/context.py` assembles requirement, plan, guardrails, the accepted-authority list, the diff and check results. A reviewer sees a diff with no architecture context; an implementer sees scope globs with no map. The Lead's reconnaissance (F8) is unscheduled; the §6.6 dogfood case (a Lead that could not find the code guessed seven globs) is the cost.

**Why it matters.** WC §1's first problem statement is that models "lose the project-level thread"; KC §8.2 to §8.4 are the answer, and they are the least implemented part of the contract. The three M6 knowledge drafts are about *experiential* knowledge (Cases and Lessons from past work); they do not cover the project map at all, so M6 as currently scoped would still leave this gap.

**Recommendation.**
- A **derived codebase map with revision-bound freshness**, generated deterministically: directory roles, entry points, build and test locations, language boundaries, generated directories, an import or include graph where a parser exists (ast-grep outlines, ctags; the research lists both). Store it as derived knowledge with `source_revision` and a path manifest; compute freshness exactly as discovery records do today (`observed_paths` changed since the revision → STALE). This is K0-class material in the drafts' terms: a reference, not a lesson.
- An **architecture map** that is model-authored, labelled derived, and bound the same way, produced by an investigator Ticket at init or on demand (`aew map refresh`), and regenerated only for the affected regions (KC §13; the Lead/operator design §6).
- **Put the maps in the packs**, bounded: the Lead gets the topology; an implementer or reviewer gets the regions their scope touches, with the freshness label. The pack generator already has the shape (`_hierarchy`, `_inputs`); this is one more section.
- Make `aew init` produce the codebase map and offer the glossary; stop shipping `UNKNOWN`.

**Lands:** small enough for M4-G (Lead UX) as the deterministic half; the architecture map as the first M6 increment. It is also the cheapest way to lower the Lead's reconnaissance cost before F8.

### G4. One harness adapter, pinned to one unversioned release (H)

**Gap.** The harness boundary is adapter-neutral by design and the conformance suite runs three drivers, but there is one real adapter, pinned to OpenCode 2.0.18, which "has no stability policy", uses an undocumented `--stdio`, and whose next release (2.0.22) is already refused (register E17). Linux has no real run outside the operator's VM.

**Why it matters.** The abstraction has never been exercised by a second implementation, so its leaks are unknown; and the project's whole live surface depends on a vendor's unversioned CLI. The conformance document already sketches Codex and Claude Code rows.

**Recommendation.** Build the second adapter now rather than at M6. Either candidate pays twice: it validates `HarnessAdapter` and `LaunchContract`, and it de-risks the pin. The Codex app-server has a native Linux sandbox (bubblewrap and seccomp, per the research) that would let M4-B's layout be compared with a vendor's; Claude Code's headless mode has explicit permission modes, setting-source isolation and hooks that map onto the projection's needs. **L** on the current protocol details of either; the conformance suite is what makes the choice cheap to get wrong. Also schedule the live smoke run the audit proposed (T4/E4) so drift is noticed before someone upgrades.

**Lands:** M4-G or alongside M6's harness-native capability work (F13 §7 needs adapters to advertise capabilities anyway).

### G5. Containment stops at the filesystem and at Linux (H)

**Gap.** Network is `not_provided` by decision (M4-B3). The provider key lives in the OpenCode server's environment inside the sandbox, so an agent that can run a shell in that sandbox can exfiltrate anything it can read (the host is bound read-only, not hidden, apart from the masked secret paths). Windows is `workdir_separation_only` and is also where the operator develops.

**Why it matters.** The documents are truthful about this, which is the main thing. But "internal alpha needs representative isolation performance and operability acceptance" (Q3) will raise network egress the first time a security reviewer looks: a contained agent with the operator's network is still a confused deputy for every internal service reachable from the host.

**Recommendation.**
- **Network namespace with a loopback-only egress proxy.** `--unshare-net`, plus a proxy on a unix socket bound into the sandbox that forwards only to the model gateway (and to the private OpenCode server, which is already loopback). The provider key then moves out of the sandbox into the proxy, which closes the exfiltration path and the N1 lead (`/proc/<pid>/environ`) in one step. This is the design the research deferred as "a sibling entry"; it deserves one. **M** on the proxy's effect on OpenCode's own fetches (the projection already disables LSP, formatter and update downloads).
- **A two-account deployment profile for internal alpha**: engine and supervisors under one UID, agents under another, with the bridge socket as the only crossing. The ADR-0005 threat model ("not an OS boundary; same UID") is the residual every security review will cite; bubblewrap's user namespace cannot change the outside UID, so this is an operator-level decision. Designing the profile now (what the supervisor needs to own, what the agent needs to read) is cheap; deploying it is not. **M**.
- **Windows:** keep the decision (M4-B4) and say so in `doctor` as a one-line fact, not a WARN that every run repeats. If Windows containment is ever wanted, a WSL2-hosted run under the same bubblewrap layout is the cheapest route; AppContainer is not.

### G6. The contract-amendment layer is becoming a second specification (M)

**Gap.** WC v0.7 and KC v0.4 are frozen and hash-pinned, which is right. Changes arrive as separate documents: the Class 0 amendment (with its own §9 amendment of KC §26), the Ticket-revision amendment (needing an ADR to amend KC §12 and WC §7, §8, invariant 7), plan assurance v0.4 (Phase 5 needs a WC amendment), the F15 note "promoted to governing before M4-E", F17's obligation "last, and only if", and the designer's decision sections inside two research documents. `docs/README.md` lists the governing order by hand.

**Why it matters.** A reader of the Workflow Contract today reads a Class 0 definition the engine does not enforce, a Ticket model without revisions, and an acceptance case (KC §26) the engine refuses. The guide is generated from policy so it cannot drift; the contract is not. Each new amendment adds a document to the "when documents disagree, the earlier one wins" chain, and the chain is now five links long before the ADRs.

**Recommendation.**
- Plan a **v0.8/v0.5 re-freeze** after M4 lands, consolidating the adopted amendments, with the manifest's own migration review. Until then, add a machine-readable **amendment index** beside `spec-pin.yaml`: each amendment, the section it replaces, its adoption date, and a test that every ADR or guide text citing an amended section cites the amendment. The map does this by hand today.
- Keep research decision sections out of the governing chain: copy the designer's decisions into a decisions record (the 2026-10-01 record is the right model) and let research stay research.

### G7. Cost is not an engine fact (H)

**Gap.** U4 (Lead usage and cost observable) is unscheduled; run records collect `usage` as telemetry, the dogfood recomputed cost from OpenCode's own database, and there is no price table, no per-unit roll-up and no budget anywhere in control state. F7's budgets (fanout, retries, cost) are M5.

**Why it matters.** Cost is the dogfood's headline number and the thing every routing decision (ADR-0010, D5), every evaluation (F19) and every Lead-efficiency claim (F15: "successful work per dollar and minute") needs. The dashboard contract reserves `/runs` with usage but has nothing to show for a Ticket or a Story.

**Recommendation.** An engine-owned **cost ledger**: per run (tokens by category, wall time, model, a USD figure from a project price table that is policy, not code), rolled up per invocation, Ticket and parent in the completion record and the parent closeout. Then a `budget.remaining` guard in `DispatchDecision` reading a policy budget per Ticket or Story: a refusal with a reason code, never an automatic cancellation. Cheap, because the predicate and the registries exist.

**Lands:** M4-G (the ledger) and M4-D (the guard), ahead of M5's wider resource governance.

### G8. Q12 is a single decision blocking five items (H)

**Gap.** Hosting, the Lead seat and session lifecycle, execution-profile resolution against a wrapper, wrapper ownership, and which native features to integrate (Q12) block F18 (bootstrap), U6 (Lead state isolation), V2 (seat held after the wrapper exits), Q11's hosting half, and the dashboard's startup integration (F20.3 "ships standalone first"). The operator-facing product surface today is `aew opencode --acquire` plus environment-variable names plus a separate `aew dashboard serve`.

**Recommendation.** Decide Q12 in the M4-D window, not after M4. The two candidates the research names (an attachable service that the organisation's launcher wrapper connects to; AEW owning the harness process per run as in M3) have different consequences for the broker, the dashboard session and the knowledge service identity. Everything downstream is cheaper once the shape is fixed. **M**.

### G9. The knowledge drafts introduce a visibility model AEW does not have (M)

See §6. In short: the three drafts assume `visibility_scope`, concealed records, cross-project corpora and service identities; AEW today is one project, one operator, one credential scheme keyed by archetype. The drafts' invariants are right, but implementing them as written would add a security model to a system that has not needed one. Recommendation: project-scoped visibility only in v1, with the composition rule kept as a cheap invariant.

### G10. The Workflow Contract has no "team" integration target (M)

**Gap.** `integrate publish` moves a local ref by compare-and-swap. The authoritative lineage of a team repository is a remote protected branch with required reviews and CI; WC §13 says external SCM state "is recorded through identifiers/status adapters and remains a separate authority boundary", and `SCM/Jira enforcement` is Designed with no date.

**Why it matters.** Internal alpha on a real repository will be a repository with a remote. Today the operator would run AEW on a local clone and then open PRs by hand, at which point `DONE` no longer means "in the authoritative lineage".

**Recommendation.** An **integration target mode** `remote_pr`: publish pushes the validated candidate branch, opens the PR through a provider adapter (GitHub, Bitbucket), records the external id on the Ticket, and the Ticket reaches `DONE` when a fetch shows the merge commit on the authoritative branch (the reconcile path already inspects git). Contract impact: `DONE` gains a second satisfying condition, so this needs an ADR-0004 amendment, not a redesign. **M**.

### G11. `aew` has no service or event model; everything polls (H)

**Gap.** `harness wait` polls a run record every 0.2 s; the dashboard polls every 10 s; capture jobs in the knowledge drafts need "committed AEW events"; the F15 note needs "event-driven safety mechanics". The engine has transaction finalizers (`TxnFinalizer`, used by archival and dispatch admission) but no durable event stream.

**Recommendation.** A **transaction outbox**: each commit appends an event record (revision, kind, ids) through the existing redo staging, so events are exactly-once with the state. Consumers (wait-any, the dashboard's SSE endpoint, the knowledge capture queue, the scheduler later) read from the outbox position they last saw. The hash-chained history manifest is almost this already for terminal events; the outbox is its hot, short-lived counterpart (bounded ring, archived with ADR-0011 rules). It makes E1 wait-any, F20's live updates and the knowledge capture trigger one mechanism instead of three. **M** on size; **H** that the three designs want the same thing.

### G12. Operator attribution recorded through the Lead is attribution, not proof (H, known)

ADR-0006 says so: `selected_by: operator` and `--decided-by operator` cannot prove a human acted. Takeover and F20.3's dashboard session use the terminal channel, so the mechanism exists. Recommendation: route operator pins, waivers and `accepted_open` concurrence (F17 D2) through the same typed-back code, as a policy option per project, before internal alpha. Small.

---

## 3. Improvements to mechanisms that exist

Smaller than §2; each is a bounded change to something built.

| # | Mechanism | Improvement | Why | Conf. |
|---|---|---|---|---|
| I1 | Containment layout | Refuse operator `containment.writable` roots that overlap the project `.aew`, the git dirs, the runs directory, the bridge directory, `/tmp`, the interpreter or any mask; add those paths to the self-test's protected probes | My area-1 F1: the only major hole in M4-B | H |
| I2 | `procs.host_pid` | Return `LookupError` when nothing matches; match the full `NSpid` chain, not the innermost | Area-1 F2; E13's evidence must not rest on a fallback | H |
| I3 | Evidence surface | `aew evidence show <id>` (E12) and results in `harness wait` are done or proposed; add a `--json` output on every read command so the typed surface of G2 has something to wrap | Four Leads opened evidence files directly | H |
| I4 | Lead permissions | Widen the headless Lead's read-only git allow-list (`ls-files`, `ls-tree`, `grep`, `branch --list`, `-C`) | O2/X3: 11 refusals of `git ls-files` in one dogfood | H |
| I5 | Protected acceptance inputs | Pin each `--acceptance-input` by digest at plan acceptance; re-verify at verification ingest and at publication; a changed digest without a Ticket revision refuses as `ACCEPTANCE_CONDITION_MUTATION` | The deterministic half of F14 Phase 2; closes T4's path mechanically for repository-local inputs without waiting for the challenger | H |
| I6 | F17's recorded query | Implement `consumer_search` as an executable query re-run at ingest (the `git grep` form) before the obligation exists | It is the one F17 piece that needs no model and no contract change, and it turns `bounded` from a word into a check | M |
| I7 | Role plan defaults | Make review-type work default to a plan-bound reviewer when the unit's class path has no review gate (V3) | The UAT-1 binding exists; Leads chose `--assurance none` on review Tickets | M |
| I8 | `aew init` | Discover the test command from `pyproject.toml`, `package.json`, `Makefile` and propose it (never configure it silently); produce the codebase map (G3) | "Checks not configured yet" blocks every gate on a fresh project | M |
| I9 | Supervisor heartbeat | Already fixed for the ending window; add a `doctor` check that the staleness limit exceeds the measured re-parse on this host | ADR-0011 made this safe at 3,000 units; a 10,000-open-unit project is unmeasured | L |
| I10 | `platform-skips.yaml` and coverage | Measure Windows coverage too and combine, now that the ratchet exists | Windows-only code (job objects, console, file-replace retries) is outside the number | M |
| I11 | Guide generation | Generate the per-archetype command reference into each role's briefing (U5) once F15's names settle | 37 `--help` lookups in 29 sessions | H |
| I12 | Dashboard transport | Use `ThreadingHTTPServer` and an SSE endpoint fed by the outbox (G11) instead of 10 s polling | Keeps the stdlib-only constraint and removes the mixed-revision window the frontend warns about at 30 s | M |

---

## 4. Upgrades: tech stack, MCP servers, skills

### 4.1 Tech stack

The stack is deliberately minimal (PyYAML, jsonschema; Python 3.11 for the Rocky 8 wheelhouse; Ruff, Pyright, pip-audit, CodeQL; coverage with a ratchet; React 19, Vite, Tailwind, React Query, Zod for the dashboard). That discipline is right for an air-gapped target and should be kept. Within it:

| Area | Upgrade | Rationale | Conf. |
|---|---|---|---|
| Hot state format | Keep YAML. Do not move to a binary or database authority | ADR-0011 removed the scale problem (H1 to H4 pass with margin); inspectability is a contract invariant | H |
| Derived indexes | Extend `local/history.sqlite` with FTS5 over history entries, evidence bodies and decisions | The knowledge drafts require a lexical baseline before any semantic provider; ADR-0011 already allows "optionally full-text"; zero new dependencies | H |
| Schemas | Generate typed Python models from the 14 JSON schemas at build time (a repo tool, no runtime dependency), or at least `TypedDict`s checked by Pyright | `dict[str, Any]` is the engine's lingua franca; Pyright standard mode cannot see record shapes | M |
| Packaging | A built wheel and a signed release artifact per accepted milestone; a `uv`/`pipx` install path; the offline bundle of research §7 as a release target | F18 bootstrap has no artifact to bootstrap from yet | M |
| CI | A self-hosted Rocky 8 runner (VM, real 4.18 kernel) for the `containment` lane and the live smoke run; the GitHub-hosted runners cannot provide the kernel M4-B's acceptance requires | The lane is run by hand on the operator's VM today | H |
| Nightly | Split the Windows serial `reference` job (over its 90-minute budget since 2026-10-01) rather than raising its timeout again | The strategy's own rule: do not hide cost by moving tests | H |
| Dashboard | Keep the contract-first discipline; add the lifecycle timeline (F20) as the next contract version, and the `ActionProjection` as the operator's decision inbox on `/attention` | Both are already reserved in the contract | M |
| Telemetry | OpenTelemetry-shaped spans for commands and runs (local file exporter; nothing leaves the host) | `AEW_PROFILE` exists; a standard shape lets the dashboard and the evaluation program share it | L |

### 4.2 MCP servers

The research note (`aew-phase6-airgap-capability-research-2026-10-01.md`) already ranks the external candidates well; I agree with its ordering and will not repeat it. Three additions, all AEW-owned, and one change of emphasis:

| Server | What | Why it is worth more than the external ones | Conf. |
|---|---|---|---|
| **`aew` (Lead surface)** | The Lead broker as an MCP server: stage tools, `explain`, `status`, `resume`, `wait_any`, one `cli(argv)` escape hatch; structured results carrying revision and `ActionProjection` | G2: removes the shell from the Lead's path, the refusal taxonomy and the ingress defect class; gives F15 its natural transport | H |
| **`aew-run` (role surface)** | The bridge's `whoami`, `check.run`, `submit` as tools, served by a thin client inside the sandbox that forwards to the supervisor | Same custody; typed report submission ends the YAML-frontmatter failure class (M3-D2, D5, D7, I5) because the schema is the tool's input schema | H |
| **`aew-knowledge`** | The drafts' `search/get/related/evidence/explain_selection`, over FTS first (arm B), K0/K1 later | Same server process as the Lead surface; the drafts' L0 disclosure text is its tool description | M |
| **Checks with structured output** | `check.run` returning counts (collected, passed, failed, skipped), the first failures with locations, and an artifact reference, not a raw log | The research's "output evidence contract"; today a verifier reads a log through a shell | M |
| **Emphasis** | Among the external candidates, build the **offline documentation** server and the **language-server** path first, before GitNexus | Local docs are "the most important airgap omission"; semantics (clangd, Pyright, tsserver) answer the Investigator's most frequent question; GitNexus has unresolved ownership and persistence remediation (SPT appendix P0) | M |

A note on context cost: an MCP server adds its tool list to every prompt. The F13 design (progressive disclosure) is the answer, but it is M6. For the Lead surface, keep the tool count near a dozen by exposing stages, not primitives, and lean on the harness's deferred-tool mechanism where the pinned release has one. **L** on the release's support; verify against 2.0.18 and whatever replaces it.

### 4.3 Skills

The package in `docs/skills/` is methodologically strong (paired A/B, selection trials separate from procedure trials, evaluator-only cases, versioned digests) and honest that nothing is evaluated. Two things limit it today: there is no delivery path (every run records its card's skills as `unavailable`), and the three candidates are reviewer and investigator techniques while the dogfood's measured failures are mostly the Lead's.

| Upgrade | Detail | Conf. |
|---|---|---|
| **A minimal delivery path now** | A project catalog `.aew/skills/<name>/SKILL.md`, hash-pinned on the invocation like cards, copied into the run's private harness state, exposed through the existing `skill` allow rule (`provided_skills` already exists in `projection.invocation_config`). No registry, no resolution, no discovery: the card names it, the run gets it, the pin proves what it got | H |
| **Skills for the Lead** | `aew-lead-operations` is the guide, and the guide already measured well (refusals 20 to 1 in 6 runs). The next three failures the dogfood recorded are Lead failures: scope selection without reconnaissance (§6.6), goals stated on mutable inputs (T4), classification by example anchoring (Q10). Each is a short skill with a negative control | H |
| **Skills for roles, from live defects** | `verification-evidence` (claims must cite AEW check ids; what inconclusive means; three live verifiers cited non-AEW checks), `report-authoring` (frontmatter, heredocs, qualified finding ids), `scope-and-reconnaissance` for implementers who discover the scope is wrong (submit `blocked` with the paths, as the §6.6 implementer did) | M |
| **Evaluate with F19** | Run the package's own protocol inside the evaluation component (G1), not beside it; the skills' `evals/cases.yaml` is the same shape as a preregistered fixture | H |
| **Skip until measured** | Language manuals (C, Python), invariant tracing as a separate skill: the package already says so | H |

---

## 5. Whole features

In the brief's "go wild" register. Each names its contract impact so that the designer can see what needs an amendment.

**F-A. The typed Lead surface and operator inbox.** (G2, G11, F15.) The MCP server, `ActionProjection` as a durable projection, the outbox feeding `wait_any` and the dashboard's `/attention`. The operator's work becomes: read the inbox, make the judgment-bearing decisions, let stages do the rest. Contract impact: none beyond F15's promotion; WC §15.6 anticipates it.

**F-B. Project maps as first-class derived knowledge.** (G3.) `aew map` with codebase, architecture, ownership and glossary classes, revision-bound, affected-region refresh, in packs. Contract impact: none; it implements KC §8.2 to §8.5 and §13.

**F-C. Replay.** Because packs are deterministic functions of recorded inputs and every transition is recorded, `aew context pack --at-revision N` and `aew replay <project> --to N` are cheap. Uses: reconstruct what a Lead or role actually saw when it made a bad decision (the T4 fixture is this); regression fixtures for the evaluation program; the "why is this in context?" view the knowledge drafts want. Contract impact: none; read-only.

**F-D. Cost ledger and budgets.** (G7.) Per-run cost, roll-ups in completion and closeout records, a `budget` guard in `DispatchDecision`, cost in `status` and the dashboard. Contract impact: none; F7's budgets get their first concrete form.

**F-E. A second harness adapter.** (G4.) Codex app-server or Claude Code headless, through the existing conformance suite, in the live lane. Contract impact: none; ADR-0009 anticipates it.

**F-F. Network containment.** (G5.) `--unshare-net` plus a loopback egress proxy holding the provider key; the label gains `network: proxy_only`. Contract impact: an ADR-0009 amendment to the label vocabulary; the isolation design's "sibling entry".

**F-G. Remote integration target.** (G10.) `integration.target: remote_pr`, a provider adapter, external ids on the Ticket, `DONE` on observed merge. Contract impact: ADR-0004 amendment; WC §13 already describes the boundary.

**F-H. Hash-pinned acceptance inputs and oracle artifacts.** (I5, F14 §10.) Beyond paths: fixtures, expected outputs, test selection and evaluator scripts named at plan acceptance, digested, and re-verified before verification counts. Contract impact: none for repository-local inputs; the full "protected evaluator" of F14 remains Phase 2.

**F-I. Model-diverse review as a measured policy.** R2 is expressible today through `routing.archetypes`. Pre-register one comparison in F19 (same corpus, reviewer from a second provider) and promote or drop it by unique defect yield and noise, as WC §20.1 requires. Contract impact: none.

**F-J. Dogfood AEW on AEW.** The register (`future-work.md`) is an Epic/Story/Ticket graph written as a 54 KB Markdown table, and the SPT appendix §9 says the Work Graph becomes the scheduling authority once AEW is operational. After containment and the remote target (F-G), AEW's own backlog is the real-repository dogfood with the richest available domain knowledge, and the only project whose ground truth the operator fully controls. The 7x cost is the honest objection; it is also the number this would drive down. Contract impact: none; a decision about where the register lives.

**F-K. Lease expiry and automatic Lead takeover.** (ADR-0005 follow-up, A2.) A Lead lease with an epoch, expiring to an operator-visible "seat available" state rather than to a silent successor; the dashboard shows it; a successor must still reconstruct from artifacts. Contract impact: an ADR amendment; WC §5 already requires explicit handoff semantics.

Features I would **not** build yet, and why: live coordination (F9) until M4-D exists and a multi-agent research dogfood shows the need (the document says so itself); sparse or overlay workspaces until a repository that needs them is in scope; dashboard write actions until the typed surface (F-A) exists, so that the dashboard calls the same tools rather than growing a second one.

---

## 6. The three M6 knowledge-system drafts

Files (untracked at review time): `aew-knowledge-capture-admission-design-v0.3.md`, `aew-knowledge-recall-context-routing-and-agent-use-design-v0.2.md`, `aew-knowledge-capture-recall-shared-semantics-v0.3.md`. All three are marked "proposal for joint review; not governing". They are not yet on the documentation map.

### 6.1 Assessment

These are the strongest design documents in the repository on their subject, and they fit AEW's authority model exactly where it matters:

- **Authority is preserved.** Providers propose; AEW admits. Knowledge text cannot grant permissions or move workflow state. Project authority is referenced by id, never copied. This is WC §6 and KC §7 applied to a new knowledge class without a new authority.
- **Case before Lesson.** Retaining structurally compressed, evidence-bound Cases (K1) deterministically, and admitting semantic Lessons (K2) only after held-out evaluation, is the right order. "NO_CANDIDATE is a successful outcome" and "caps are maximums, never quotas" are the two sentences that will keep the store from filling with model impressions.
- **Source class is tied to containment.** `ENGINE_OBSERVED_CONTAINED` versus `ENGINE_OBSERVED_WEAK_BOUNDARY` versus `ROLE_ATTESTED` makes M4-B's label a precondition for default serving. That is a better use of the containment label than any other document makes.
- **Immutable content, append-only disposition.** Separating `knowledge_id + version` from the disposition fold, with per-record and global sequence numbers, is the ADR-0011 discipline applied to knowledge.
- **The acceptance gate is the right one.** "Agents find and use relevant prior experience unprompted, improve independently verified outcomes, and abstain when history is irrelevant" measures the product, not the plumbing; the phased arms (A/B/C before D/E) and the separation of writer, retriever, router and reader failures are sound experimental design.
- **Admission does not imply serving; retrieval never upgrades authority; counterevidence travels with advice.** These are the invariants a memory system usually lacks.

### 6.2 Issues to resolve before adoption

| # | Issue | Why it matters | Suggestion | Conf. |
|---|---|---|---|---|
| K1 | **Storage is unplaced.** The drafts put capture jobs, candidates, dispositions and receipts in "dedicated durable/cold knowledge-history structures", outside hot control state, but do not say whether they join the ADR-0011 manifest (one hash chain, one audit, one derived index) or form a second store with its own integrity | ADR-0011's invariants (commit-time history independence, hash pinning from the hot root, incremental and full audit) either cover knowledge or they do not. A second chain means a second audit path and a second `cold.root` | Make knowledge records new entry kinds in the existing manifest (`case`, `lesson`, `disposition`, `receipt`), extend `history.schema.json` and the SQLite index (with FTS). One integrity story. Write the ADR | H |
| K2 | **Capture triggers need a durable event source.** "Capture begins from committed AEW events"; the engine has finalizers but no event stream; at-least-once capture with idempotent admission is promised | Without an outbox, the capture queue either polls hot state (an ADR-0011 history-independence violation in waiting) or is coupled into the commit path | The transaction outbox of G11; the capture worker consumes it | H |
| K3 | **Visibility scope is a new security model** (`visibility_scope`, concealed records, cross-project, "most restrictive root", scoped-before-top-k, leak through counts and hints) | AEW is one project and one operator today; nothing else in the system has a visibility concept. This is the largest new surface in the drafts, and the one with no present use case | v1: visibility is the project; keep the composition rule and "scope before limits" as stated invariants so the schema does not foreclose them; defer multi-scope to a hosting decision (Q12) | M |
| K4 | **Service identity** for capture and admission needs a new credential kind | ADR-0005 credentials are scoped by archetype role table and Lead generation; the drafts want enumerated operations, no Lead credential, unreachable from worker shells | Model it on F20.3's operator-session credential: a kind in the schema-versioned `lead` record, `expires_at`, revoked on takeover like everything else; its allowed operations are a role table | M |
| K5 | **Vocabulary collisions.** `disposition` (here: admitted/held/rejected) versus F17's dispositions (bounded/known_limit/follow_up/accepted_open) and ADR-0007's closeout dispositions; `supersedes` here (scoped default replacement) versus hierarchy supersession and plan supersession; `serving eligibility` versus evidence admissibility (D4: UNCHANGED/REVALIDATE/INVALIDATED/SUPERSEDED/HISTORICAL) | The drafts rightly refuse new invariant namespaces; the words need the same discipline. KC §8.5 asks for a glossary and there is none | A glossary pass before freezing, and `knowledge_disposition` or similar where a word is already taken | H |
| K6 | **W04 and W05 are frontend work packages,** referenced as "the W04 context/receipt design" and "W05 Evidence inspection", with demo-only preview schemas (`investigation-preview-0.1.0.json`) | The drafts say preview schemas are proposals; the risk is that a frontend fixture shape becomes the backend's wire semantics by familiarity | Keep the receipt chain (`MATCHED → SELECTED → PREPARED → DELIVERY_ACKNOWLEDGED → CITED → BENEFIT_EVALUATED`) as the engine's model and make the frontend adopt it, not the reverse; today's engine already has the first two in a weak form (the pinned pack sha and the delivered contract) | M |
| K7 | **The research basis is not in the repository** (`aew-knowledge-capture-admission-and-agent-usefulness-2026-10-03.md`) | Joint review needs it; the map's test requires every document to be listed | Add it, or the drafts, to `design/proposals/` and the map, with a register entry | H |
| K8 | **M6 is overloaded.** The map says M6 is capability manifests and progressive disclosure (F12, F13); the drafts target "the M6 knowledge system"; the airgap research adds a toolchain bundle | Three programmes under one milestone label, each gated on evaluation | Split: M6a capabilities and skills delivery; M6b knowledge (arm B first, see below); the bundle as release engineering across both | M |
| K9 | **The cheapest increment is already buildable.** Arm B (guarded explicit raw-history recall) needs `aew history search` over FTS, request-mode labelling and the untrusted-data framing the packs already use for `history load` | Measuring B before designing K1 templates further is what the drafts' own phase 1 asks for | Build B as the first M6b increment; replay K1 templates over M1 to M3 history (the drafts' §24) as the second | H |

### 6.3 Two smaller points

- The recall draft's **context budgeting order** (mandatory instructions, current work and authority, current source and evidence, then recall) should be written into the pack generator as a rule now, before any recall exists, so that later recall cannot displace the guardrails section by accident.
- The capture draft's **"workflow disposition is not proof"** (a `known_limit` label does not establish the observation was harmless) is the F17 insight in another place. The two should cite each other, and F17's `accepted_open` observations are an obvious K1 Case template.

---

## 7. What looks sound and should be left alone

- **The authority model, end to end.** Single commit point, verifier-only credentials, generation fencing, operator-at-terminal takeover, custody bridges, run rotation. Every independent review attacked it; the fixes were implementation corrections, never model changes.
- **Evidence binding.** Fingerprints, definition digests, plan and attempt and candidate bindings, computed staleness. The Ticket-revision decision (D1: field-group digests) extends it without changing it.
- **Hot and cold state.** ADR-0011's property, measured on three platforms with margin, and the P3 review's index-authentication fix. Do not revisit the storage choice.
- **Dispatch legality.** One predicate, a registry, enforcement at commit, reason codes and primitive declarations. M4-D and M5 should consume it, not fork it.
- **The testing strategy.** Lanes by directory, one assurance gate, deterministic regressions never demoted, exploration seeded, the oracle, review probes preserved unchanged. The best part of the engineering process.
- **The documentation discipline.** Status by folder, a map enforced by a test, generated guides, pre-registered rubrics, decisions recorded as given. The amendment chain (G6) is the one strain on it.
- **The decision to keep mutating concurrency at 1 until isolation is real,** and to label containment truthfully everywhere.
- **The harness boundary's three rules** (the adapter never commits control state; agent-to-AEW traffic uses engine operations through the bridge; harness-to-AEW traffic is telemetry no gate reads). Keep them when the surface becomes MCP.

---

## 8. Sequencing

An overlay on the approved M4 phases, not a replacement. Items in **bold** are from this review.

| When | What | Why here |
|---|---|---|
| **M4-C** | Workspaces for N > 1 as planned; I1, I2 (containment fixes) | Before any run relies on the label |
| **M4-D** | Queue and lease as planned; **the outbox (G11)**, wait-any on it; **cost ledger and budget guard (G7)**; **Q12 decided** | The outbox is the one mechanism the queue, wait-any, the dashboard and knowledge capture all want; Q12 blocks five items |
| **M4-E** | Promote F15; **stage commands delivered as the `aew` MCP server (G2)**, with the role bridge as `aew-run`; `ActionProjection` to the dashboard's `/attention` | F15's natural transport; removes the ingress class |
| **M4-G** | U1, U8, V1, V2, V4, E12 as planned; **I3 to I8**; **the minimal skills path and the Lead skills (§4.3)**; **the deterministic codebase map (G3)** | Lead UX is where the measured friction is |
| **M4-H** | **F19 as a component first (G1)**, then the preregistered dogfood with the incident corpus and one external comparator; **F-C replay** for its fixtures | The dogfood the plan already requires, with a harness that outlives it |
| **Between M4 and M5** | **The re-freeze (G6)**: WC v0.8, KC v0.5 consolidating Class 0, Ticket revisions, F15, the Ticket-revision ADR; the amendment index until then | Before M5's scheduler reads the contract |
| **M5** | Scheduler as planned on `DispatchDecision` and `ActionProjection`; F7 budgets on the ledger; **F-E second adapter** in the live lane | A second adapter before the scheduler assumes one harness's behaviour |
| **M6a** | Capabilities, progressive disclosure, skills registry (F12, F13, D3); **docs and language-server providers first (§4.2)** | The research's own priority |
| **M6b** | **Knowledge: arm B (`history search` over FTS) first**, then K0/K1 with the K1 template replay, with the drafts adopted after the §6.2 issues; the glossary pass | The drafts' phase 1 |
| **Before internal alpha** | **F-F network containment**, **F-G remote integration target**, the two-account profile (G5), terminal-channel operator pins (G12) | The questions a security and a team review will ask first |

---

## 9. Process notes

- **Velocity and the bottleneck.** 302 commits in nine days of history (the repository begins at the 2026-09-25 freeze), 79 on 2026-10-03, with an independent review per PR. The quality control is the review cadence, and the operator and designer are its serial path: every open question in the register waits on one of them. The typed Lead surface (G2) and the operator inbox (F-A) are also the way to keep that path short when AEW runs itself.
- **The register is a work graph in a table.** `future-work.md` is 54 KB of Markdown with targets, gates, sources and a closed section; it is Epic/Story/Ticket data. F-J says what to do about it eventually; until then a structured form (YAML with a rendered view, which the dashboard could show) would make the milestone-start triage rule mechanical.
- **Docs to code ratio.** About 1.7 MB of documentation for about 20 k lines of product code. The documents are good, and the map keeps them findable; the re-freeze (G6) is the point at which to retire what the ADRs have absorbed.
- **The evaluation habit is the project's best process asset**: pre-registered rubrics, amendments recorded before the runs they govern, failures and invalid runs kept, "two trials per cell is a direction, not a rate". G1 asks only that it get a home in the code.
- **What I could not assess.** Whether the organisation's gateway exposes the features (tool search, structured output, caching fields) that §4.2 and F-A would lean on; whether OpenCode's current release still fits the adapter; the performance of the knowledge drafts' recall on the target hardware. Each is marked **L** above and is a probe, not a design question.

---

## Appendix A. Documents read

Governing: `agent-engineering-workflow-design-v0.7.md`, `aew-knowledge-contract-v0.4.md`, `spt-agent-toolchain-remediation-v0.2.md`, `aew-spec-manifest-v0.2.yaml`, `spec-pin.yaml`; `design/workflow-contract-amendment-class0-2026-10-01.md`, `design/plan-assurance-and-classification-decisions-2026-10-01.md`, `design/plan-assurance-and-premise-validation-design-v0.4.md`, `design/ticket-revision-amendment-2026-09-30.md`, `design/aew-two-interaction-surfaces-idea-v0.4-2026-10-01.md`, `design/failure-class-registry.md`, `design/invariant-index.md`, `design/dashboard-api-v1-provisional.yaml` (paths and header); ADR-0001 to ADR-0011.

Living: `implementation/implementation-status.md`, `implementation/future-work.md`, `implementation/m4-ambiguity-report.md`, `implementation/testing-and-ci-strategy.md`, `implementation/harness-conformance.md`; the four guides.

Proposals and research: all seven proposals; all five research notes.

Skills: `skills/README.md`, `specification.md`, `authoring-guide.md`, `evaluation-guide.md`, `templates/SKILL.md`, `candidates/adversarial-review/SKILL.md`.

Archive (evidence): `m3-dogfood-report.md`, `m3-evidence-synthesis.md`, `m3-audit-findings.md`, `m3-independent-audit-2026-09-29.md`, `review-response-2026-10-01.md`, `ticket-revision-amendment-review-2026-09-30.md`, `adr-0011-reviewer-brief.md`, `adr-0011-implementation-plan.md` §7.4, `adr-0011-storage-investigation-2026-10-01.md` §1 to §3, `external-agent-workflow-lessons-2026-09-28.md`.

Dashboard: `web/README.md`, `web/DESIGN.md`, `web/UX-CONTRACT.md`, `web/docs/aew-readonly-dashboard-design-v0.2.md` (opening), `web/docs/integration-checklist.md`, `web/docs/design/plans/w04-comparison-context.md`, `web/package.json`.

Code sampled: `src/aew/knowledge/{context,manifest}.py`, `src/aew/harness/opencode/projection.py`, `src/aew/engine/{dispatch,reasons,primitives,api}.py` (openings), `src/aew/roles/archetypes/{implementer,reviewer,lead}.yaml`, `src/aew/roles/cards/{python_engineer,security_reviewer}.yaml`, `src/aew/cli/*.py` (command table), `pyproject.toml`, `.github/workflows/{ci,nightly}.yml`, `tests/platform-skips.yaml`.

The three drafts as reviewed: capture/admission v0.3, recall/context-routing v0.2, shared semantics v0.3.
