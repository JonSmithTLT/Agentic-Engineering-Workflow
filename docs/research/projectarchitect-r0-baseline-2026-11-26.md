# ProjectArchitect concepts: the R0 baseline and overlap (2026-11-26)

**Status:** research record, 2026-11-26. It is R0 of the
[ProjectArchitect concept research and evaluation plan](projectarchitect-concepts-and-evaluation-2026-11-25.md) (§9,
"Baseline and overlap" and the "Lead's first assignable task"), which the operator approved for filing with R0 on
2026-11-26 ("Yup file and run r0."). It is read-only: no model ran and no product code changed. It is evidence for the
experiments' row, E389, and decides nothing: every proposal below is the operator's to place when E389 runs.

**Basis.** AEW `main` at `eece01e5`, the revision the plan itself pins. Every `file:line` below is at that commit.

## Summary

The checklist has 31 items: the plan's brief elements (§5.1, 8 items), its question-scoped retrieval fields (§5.2, 10),
its continuation categories and recovery requirements (§5.3, 9), and the concepts C5 to C8 (4).

| Class | Count | Meaning here |
|---|---|---|
| **Already present** | 19 | The code supplies the field or behaviour reliably at `eece01e5`, as rendered or read below |
| **Deficient** | 10 | Absent, or present only in part, with the gap shown |
| **Unverified** | 2 | Could not be settled by reading and rendering; needs a run or a decision |

"Already present" says the field exists and is delivered. It says nothing about whether a worker uses it well: that is
what Experiments A to C measure, and is unverified for every item.

The three candidate deltas most worth testing (§"Candidate deltas" gives all five):
1. **D1, a recovery section in a replacement invocation's pack** (C4; owner F36). After an interruption with partial
   work, the replacement implementer's pack was byte-for-byte its predecessor's except for the invocation id and the
   inputs fingerprint: nothing said a predecessor existed, how it ended, or what it left in the workspace.
2. **D2, open questions and limitations carried into the pack** (C3; owner E198). The pack has no section for them, and
   the consumed-inputs summary drops a discovery record's `unresolved_questions` and a research record's `uncertainties`.
3. **D3, a selection and omission manifest in the pack** (C3; owner E368, with F35). What was selected is recorded on the
   invocation, never shown in the pack, and a knowledge item the role names but the pack does not deliver is silently
   left out of the contract's own list. This is E368's core-plus-pointers shape, so it is E368's rewrite measured by C1.

For E368: judge its rewrite by C1, what the worker then achieves, not by the bytes it saves (§"Where E368's rewrite
should use C1").

## Method

**What was rendered.** A scratch probe (not committed) drove the real CLI over the test suite's sample project
(`tests/helpers/aewflow.py`: `sample_project`, a two-module `calc` repository with a `unit` check):
1. a planned class-1 Ticket, T-0001 "Add subtract()", dispatched to an implementer (the `engineer` card, v4) as
   INV-0001, and its pack read with `aew context show`;
2. map reads at the same basis through the CLI, which answers through the same query module as a worker's bridge reads
   (`src/aew/cli/map_commands.py:120-122`: outside a worker run it calls `query.serve`, inside one the bridge, which answers from the same module);
3. partial work in INV-0001's workspace: one change staged, one more unstaged, one file untracked;
4. a Lead checkpoint with a note and a next action, then an operator takeover that interrupted INV-0001;
5. `aew resume` (text and JSON), `aew status T-0001`, the handoff file;
6. a reconcile to RUNNING and a replacement implementer, INV-0002, whose pack was compared with INV-0001's;
7. a finished implementation and a reviewer's pack (INV-0003).

A second probe ran `aew init` on a throwaway copy of AEW itself at `eece01e5` and asked the map one multi-file question.

**Reproducing it.** The probe was an integration test placed beside `tests/integration/test_context_packs.py`, using
its imports, run once with an absolute `PYTHONPATH` to the checkout's `src`, and removed. Each step above is one CLI call
named in this record; no fixture or helper was changed.

**What was not run, and why.**
- No model, so nothing here says whether any field helps a worker.
- No contained (bubblewrap) run, so a contained run's private index is read from code, not observed.
- No worker bridge call: the CLI is the same query module (the module's docstring states the parity); the bridge's own
  tests hold it.
- The lexical map route: this host lacks the pinned ripgrep 15.1.0 payload (`aew init` listed it as missing and
  needed), so every lexical question answered `NOT_SUPPORTED`. That answer is correct (it is not `NOT_FOUND`), and it is
  a preflight item for Experiment B.

## The three inspected artefacts

### A current pack and worker handoff

INV-0001's pack (6,141 bytes) and INV-0003's reviewer pack (6,765 bytes) are rendered by
`src/aew/knowledge/context.py` from durable artifacts only (its module docstring), in document order: the launch
contract (`_launch_contract`, `context.py:339`), the role card (`:238`), the requirement with goal-backwards and
contract criteria and the Ticket scope (`:435-476`), the accepted plan, guardrails, governing authority (`:492`),
checks (`:499`), open findings (`:507`), the role's evidence sections and, last, the structural map slice (`:763`).
The selected sources, with their sha256, are recorded on the invocation (`src/aew/engine/context_ops.py:341-356, 374`),
not in the pack. Production renders with no budget (`context_ops.py:371`: `ctxmod.render(inputs)`), so the tiered
budget and its notice (`context.py:814-829, 853-893`) never run there.

A worker gets two more texts with the pack: the run's system text (`src/aew/harness/opencode/projection.py:242-281`,
whose line `:256` is one of E368's false lines) and the run preamble (`src/aew/harness/contract.py:349`). E368 owns
their consistency; this record checks only what the plan's brief elements need.

### A multi-file retrieval task

The question, a real one this record needed: *what does a replacement implementer see after its predecessor was
interrupted with partial work?* Answering it took five files: `knowledge/context.py`, `engine/context_ops.py`,
`engine/lead_ops.py`, `engine/resume_ops.py` and `harness/containment/layout.py`.

What the map gave, on the copy of AEW:
- `map.search resume_ops.py` and `map.search context_ops.py`: `SATISFIED`, structural, coverage complete (every tracked
  path at the basis), one path each, no line.
- `map.search write_handoff`: exact path resolution found nothing, then the lexical route answered `NOT_SUPPORTED`
  ("EXACT_CODE_SEARCH is UNAVAILABLE"), coverage incomplete, never `NOT_FOUND`.
- Relations and code facts are declared `NOT_SUPPORTED (not built)` (`src/aew/maps/query.py:205`), so "who calls
  `write_handoff`" has no map answer.
- Every answer's next step is the source: "read the source in your workspace with your own tools" (`query.py:75`).

On the sample project the same envelope held its distinctions: `calc/nothere.py --kind path` answered `NOT_FOUND` over a
complete domain; `core.py` was `SATISFIED` by suffix; `map show --scope ticket` listed the Ticket's three directories
with the one out-of-scope directory counted in `omitted.by_scope`.

So today a worker answers a multi-file question with path lookups from the map and its own source reads. The existing
question-scoped route is an **investigator Ticket**: the investigator writes a `discovery_record` (`question`, `facts`
each with `evidence`, `hypotheses` with `confirm_by`, `unresolved_questions`, `observed_paths`;
`src/aew/schemas/evidence.schema.json:100-113`, template `context.py:59-70`), and a consumer's pack shows it as an input
with its freshness, which turns STALE when an observed path changes (`context.py:541-552`). That route is the B1 arm the
plan's Experiment B needs; no new helper has to be built to run it.

### An interrupted task record

Observed in order:
- The checkpoint wrote `state/handoffs/H-0001.md` (`aew/handoff/v1`; `src/aew/engine/lead_ops.py:446-487`): the
  outgoing generation, the base revision, the work graph, the in-flight invocations ("INV-0001 (implementer for
  T-0001)") and the Lead's note, ending "This summary does not replace the artifacts it references; reconstruct with
  `aew resume`."
- The takeover revoked INV-0001 and moved T-0001 to INTERRUPTED from RUNNING, since its phase waited on that invocation
  (`lead_ops.py:148-179`).
- `aew resume` gave the next action "inspect workspace/artifacts and reconcile (interrupted in RUNNING); success is never
  assumed" (`resume_ops.py:395-397`) and the Lead's next-action line. Its JSON (and the Lead's typed `resume` tool,
  `src/aew/surface/run.py:96-99`) carries the handoff's full text (`resume_ops.py:589-592, 623`); the CLI text view
  (`render_resume`, `resume_ops.py:653-689`) prints only the next-action line, not the note.
- The workspace kept the partial work: `MM calc/core.py` and `?? tests/test_partial.py`, before and after the takeover.
- Leaving INTERRUPTED takes a reconcile with a reason, to a phase no later than the interrupted one
  (`src/aew/engine/transitions.py:126-129`).
- The replacement implementer's pack, INV-0002 against INV-0001, differed in two lines only:

```text
1c1
< # AEW launch contract — INV-0001 (Engineer — implementer)
---
> # AEW launch contract — INV-0002 (Engineer — implementer)
12c12
< - Evaluated snapshot: base `6ac9b09…`, inputs `git-tree:e96fdfe…`, workspace `ws-T-0001-1`
---
> - Evaluated snapshot: base `6ac9b09…`, inputs `git-tree:49ba21e…`, workspace `ws-T-0001-1`
```

- In a contained run, `git add` stages only into the run's private index, which is scratch and ends with the run
  (`context.py:414-416`; `src/aew/harness/containment/layout.py:888-905`): staging is not part of AEW's workspace
  model, since AEW commits the files. Read from code, not observed here.
- A harness run that ended or was lost is not an interruption: the invocation keeps its authority, and `resume` lists
  the run's state and evidence (`src/aew/engine/harness_ops.py:953-977`).

## The checklist

Each item is classified **present**, **deficient** or **unverified**, with its evidence at `eece01e5`.

### Brief elements (plan §5.1)

| # | Element | Class | Evidence |
|---|---|---|---|
| B1 | Task objective and explicit exclusions | present | Requirement, title, body and scope (`context.py:435-476`); Prohibited (`:373`); the contract criteria ("changes stay within calc/ and tests/") |
| B2 | Acceptance conditions and verification method | present | Goal-backwards and contract criteria (`context.py:444-449`); completion criteria per role (`:400-432`); available checks (`:499-505`) |
| B3 | Relevant settled constraints | present | Guardrails, governing authority (`context.py:492-496`), inherited obligations and corrections (`:521-539`), the accepted plan pinned by sha256 (`:359`) |
| B4 | Source basis and evidence locators | present | Evaluated snapshot (`context.py:357`); check results with evidence ids and logs (`:514-519`); the map slice's commit and freshness; sources with sha256 on the invocation (`context_ops.py:341-356`) |
| B5 | Dependency outcomes and their status | present | Consumed inputs with freshness, basis and acknowledgement, and "Recheck consequential claims" (`context.py:541-552`); a verifier reads implementer claims as "NOT evidence" (`:760`) |
| B6 | Open questions and known limitations | **deficient** | No pack section holds them; `_input_summaries` keeps facts, hypotheses, conclusions and subjects but drops `unresolved_questions`, `uncertainties` and `constraints` (`context_ops.py:74-89`); `open_questions` is undelivered (E198) |
| B7 | Selection and omission manifest | **deficient** | The selection is recorded on the invocation (`context_ops.py:374`), not in the pack; omissions show only under a budget cut (`context.py:814-829`), which production never makes (`context_ops.py:371`); the contract's "Required knowledge (included below)" lists only what was delivered and silently drops the rest (`context.py:363-364`) |
| B8 | Required return information | present | Report kind, template and allowed values from the schema (`context.py:384-398`); completion criteria; the consistency of the three texts is E368's |

### Question-scoped retrieval (plan §5.2)

Classified against the existing helper form, an investigator Ticket and its `discovery_record`, which consumes the map
envelope and ordinary source reads.

| # | Field | Class | Evidence |
|---|---|---|---|
| R1 | Request: the question | present | `discovery.question` (`evidence.schema.json:105`); the Ticket's title and body |
| R2 | Request: permitted scope | present | Ticket scope; an observation dispatch is read-only and any workspace change refuses the submission (`context.py:360-362`) |
| R3 | Request: source and working-state identity | present | The observation commit and tree as a pack source (`context_ops.py:343-345`); a map answer's `basis` |
| R4 | Request: answer intent | unverified | No field; only the Ticket's acceptance criteria could carry it. Whether that suffices is a question for Experiment B |
| R5 | Request: resource budget | **deficient** | Nothing in the pack states a budget to the role (no budget in production, `context_ops.py:371`); run-level limits exist but are not part of the request |
| R6 | Response: concise answer, facts apart from hypotheses | present | `facts` with `evidence`, `hypotheses` with `confirm_by` (`evidence.schema.json:106-111`); carried to consumers as `fact:` and `hypothesis:` lines (`context_ops.py:81-82`) |
| R7 | Response: source spans and source identity per claim | **deficient** | A fact's evidence is free strings (`evidence.schema.json:107-108`); a lexical map hit has a path and line "of the workspace at query time" with no content identity (`query.py:440, 531-533`) |
| R8 | Response: the domain searched, excluded and unsupported | **deficient** | The map envelope has it (`coverage`, `omitted`, `unsupported`: `query.py:51-52`); a `discovery_record` has no such field (`evidence.schema.json:103-113`), so a helper's negative answer cannot state its domain |
| R9 | Response: terminal and status distinctions, incomplete searches included | present | Record results `pass`, `blocked`, `inconclusive` (`src/aew/knowledge/evidence.py:154`); the map's four terminals, `NOT_FOUND` only over a complete domain (`query.py:46-47`) |
| R10 | Response: a next step when unsupported | present | `unresolved_questions`, `confirm_by`; every map answer's `next` (`query.py:75-76`) |

### Continuation and recovery (plan §5.3)

| # | Category or requirement | Class | Evidence |
|---|---|---|---|
| K1 | Verified completion against a stated state | present | Check evidence sealed to the snapshot; unmet gates per Ticket in `resume` (`resume_ops.py:560`) |
| K2 | Unfinished work: which files or actions remain | **deficient** | Nothing records it, and the replacement pack is silent (the two-line diff above); the Lead is told only to "inspect workspace/artifacts" (`resume_ops.py:396`) |
| K3 | Investigation state: current against rejected hypotheses | **deficient** | The Lead's checkpoint note is free text (`resume_ops.py:691-698`); a worker has no channel (F36's handoff note is not built); a `discovery_record` has hypotheses but no rejected ones |
| K4 | Pending work: active children, queued handbacks, unread results | present | The handoff's in-flight invocations (`lead_ops.py:472-474`); `resume`'s harness runs with their evidence (`harness_ops.py:953-977`); the Lead's wakes in `aew status` (`resume_ops.py:700-714`) |
| K5 | Recovery observation: reconstructed against recorded | present | `resume` rebuilds from durable artifacts in the Knowledge Contract's order (`resume_ops.py:52-56`) and lists contradictions; the handoff says it does not replace them. The CLI text view omits the handoff's note (`resume_ops.py:653-689`); the JSON and the typed tool carry it |
| K6 | Next action | present | `checkpoint --next` (`resume_ops.py:691-698`); deterministic next actions per unit (`resume_ops.py:395-397`) |
| K7 | Staged, unstaged and untracked work covered, or what was not preserved stated | **deficient** | The worktree kept unstaged and untracked work (observed); a contained run's staging is scratch (`layout.py:888-905`); nothing records or states either to a successor |
| K8 | Bound to task, attempt, source state and custody | present | The handoff's generation and base revision (`lead_ops.py:456-462`); each invocation's snapshot, workspace and attempt |
| K9 | Custody reconciled before a new worker or a completion claim | present | INTERRUPTED leaves only by a reasoned reconcile, never past its phase (`transitions.py:126-129`); a lost harness run is not an interruption (`harness_ops.py:957`) |

### C5 to C8

| # | Concept | Class | Evidence |
|---|---|---|---|
| C5 | Outline, then bounded source reads | **deficient** | No outline: map sections are directory-level, relations and code facts `NOT_SUPPORTED (not built)` (`query.py:198-205`). The plan defers it to the semantic roadmap (F22.2) |
| C6 | Compact running-task digest | present | `aew status`'s work graph (`src/aew/knowledge/render.py:60`) and the Lead's wakes; `resume`'s harness runs |
| C7 | Decision retrieval with supersession | **deficient** | Decision records (`src/aew/engine/base.py:524-560`) carry no supersedes link; plan revisions keep their history; `aew history links` follows provenance. The plan says inspect before building, and nothing here shows a gap that costs work |
| C8 | Repeated reads and context waste | unverified | The Lead's typed-tool log records calls with argument digests (`src/aew/harness/tool_calls.py`); worker transcripts are kept under F19's retention; no repeated-read measure exists. E369's audit is the standing owner of the diagnosis |

## Proposed fixture set

The plan's planning figure is eight fixtures and three repetitions per arm (§8.1). Each fixture below is public or
synthetic; held-out material stays under F19's rules. "Existing" means it is in `eval/experiments/` or the test helpers
at `eece01e5`.

**Experiment A (brief effectiveness), 8 fixtures:**

| Id | Family | Fixture | Source |
|---|---|---|---|
| A-F1 | Local fix | A seeded case of the lower-bound lane (Python-Markdown 3.11.0, 480 files) | Existing: `eval/experiments/lower-bound-qualification/` |
| A-F2 | Change spanning modules | A new seeded case on the same pinned repository, touching two modules | New, R1 |
| A-F3 | Regression against a prior decision | The context-pack rehearsal's fixture, where `queued` supersedes `waiting` | Existing: `eval/experiments/context-pack-rehearsal/` |
| A-F4 | Dependency handback | A Ticket consuming an investigator's `discovery_record` that holds an unresolved question the change depends on | New, R1 (exercises D2) |
| A-F5 | Stale or misleading context | A-F4 with an observed path changed after the record (input STALE), and a map STALE against the base | New, R1 |
| A-F6 | Verification brief | The verifier-disposition cases VD-1 to VD-3 | Existing: `eval/experiments/verifier-disposition/` |
| A-F7 | Re-review with open findings | A review with one required finding, then a fix | New, R1, on the sample project |
| A-F8 | Predecessor's partial work | R0's interrupted case (staged, unstaged, untracked) | New, R1; shared with C-4 |

**Experiment B (retrieval), the plan's eight cases** on Python-Markdown 3.11.0, except B-F3:

| Id | Case | Question shape |
|---|---|---|
| B-F1 | Simple exact path or local fact | Where is a named module; what a constant's value is |
| B-F2 | Several source files | How an extension registers and runs, across three files |
| B-F3 | Small directory past the global cap | E293's 207-directory reproduction (`z_task`), on its own synthetic fixture |
| B-F4 | Complete search, no match | A symbol that does not exist, under `--kind path` and lexically |
| B-F5 | Capped or exhausted search | A common token past `--limit` and past the lexical time bound |
| B-F6 | Stale map or modified workspace | An uncommitted edit that changes the answer; a map one commit behind |
| B-F7 | Unsupported semantic relation | "Which functions call X" |
| B-F8 | Numeric or configuration fact | A default with its unit and the setting that changes it |

**Preflight for B:** the host must hold the pinned ripgrep payload, or every lexical case answers `NOT_SUPPORTED` (as on
R0's host).

**Experiment C (continuation), the plan's six cases**, functional first with scripted roles over `aewflow`, as R0 did,
and a model trial only where a functional test cannot decide:

| Id | Case | Functional form |
|---|---|---|
| C-F1 | Planned rollover | `checkpoint`, `lead handoff offer` and `accept` |
| C-F2 | Parent ends before reading a finished child's report | A takeover after a run ended with evidence (`harness_ops.py:975-977`) |
| C-F3 | Restart while a child is live or its state is unknown | A live and an unreadable run record at `resume` |
| C-F4 | Staged, unstaged and untracked work | R0's probe, plus a contained run on Linux |
| C-F5 | A rejected hypothesis whose evidence would be lost | Needs a model trial: no channel holds it today (K3) |
| C-F6 | Several continuations | Two checkpoints: both handoffs kept and the latest shown |

## Candidate deltas

Each is a proposal for its owner to take or refuse; none is built here. Each is tested by changing only it (plan §5.1).

| Id | Delta | Gap | Owner | Tested by |
|---|---|---|---|---|
| D1 | A replacement invocation's pack gains a short, AEW-assembled recovery section: the predecessor invocation, how it ended and why, its evidence ids, and the workspace's paths changed against the base and untracked at dispatch, labelled as an observation of the workspace, never a claim, and saying that staging is not preserved | K2, K7 | F36 (its recitation already names "changed files against the planned scope"); a narrow slice for replacements | C-F1, C-F4; A-F8 |
| D2 | Consumed inputs keep their `unresolved_questions`, `uncertainties` and `constraints` as labelled lines, and the pack gets an open-questions section | B6 | E198 (its follow-on names `_input_summaries`) | A-F4, A-F5 |
| D3 | The pack lists what it holds and what it points to: each selected source, and each knowledge item the role names but this pack does not deliver, with the reason and the command that reads it | B7 | E368 (core plus pointers; "references that resolve"), with F35 (the derived-section convention) | A, as the whole of E368's rewrite against today's pack |
| D4 | A `discovery_record` may state the domain it searched, what it excluded and what was unsupported, so a helper's negative answer is bounded | R8 | None open; resolve at R5 | B-F4, B-F5, B-F7; add only if B shows false negatives |
| D5 | The CLI's `resume` text prints the latest handoff's note | K5 (the text view) | F8 (checkpoints) or a row at R5 | C-F1, C-F6 |

Not proposed: a retrieval service, an outline index (C5 stays on F22.2), a decision store (C7), or a memory system.

## Run accounting and resource cap

**Accounting**, per attempt, in F19's attempt ledger (`aew/eval-attempt/v1`), every attempt registered before launch:
- each participant's calls apart: parent, worker, helper (B1's investigator), verification, downstream consequence run;
- tokens in, out, cache read and cache write as observed, never assumed;
- billed cost as F25's settled figure where it exists, a price-equivalent estimate in its own field, unknown as unknown,
  never zero;
- wall time end to end, including waits and recovery, as a distribution;
- tool calls and source reads per participant (the session-observable half waits for F19's session reader, D2 of the
  agent-effectiveness delta, which is not built; until then it is recorded as not measured);
- retries, escalations, operator interventions and infrastructure failures, counted and never excluded;
- preparation (map generation, fixture builds) apart from warmed execution, and included in the total.

**A proposed cap, for the operator to set at preregistration** (F19 pins budget there):
- one worker profile per experiment, already qualified: the lower-bound lane's `opencode/gpt-5-nano#high` cost $0.066
  for its whole qualification run, and `lbq-v2-deepseek-v4-1-flash` $0.22 for six ceiling runs;
- at most $0.50 and 20 minutes per top-level attempt, helpers and consequence runs included;
- at most 132 top-level attempts: A 48 (8 x 3 x 2 arms), B 48 (8 x 3 x 2), C at most 36 model attempts (6 x 3 x 2),
  most of C being functional and free;
- a hard total of $75, the worst case of 132 x $0.50 with margin, and a stop for review at half of it. At the lane's
  observed rates the expected spend is a few dollars.

## Predeclared decision criteria

Set before any treatment result is seen (plan §8.5). Mandatory constraints, evidence and custody are pass or fail. "Not
worse" allows one attempt in 24 per family as the quality tolerance.

**Experiment A** (A0 today's pack; A1 one named delta, or E368's rewrite):
- **Fail, whatever else:** any attempt in A1 that breaks a mandatory constraint (scope, prohibited, guardrails) where
  the same attempt in A0 did not.
- **Adopt** (a narrow change, routed to its owner) only when A1's verified completions are not worse than A0's in every
  task family, **and** at least one preselected measure improves by its minimum useful benefit: additional source reads
  per verified completion down 20%, or cost per verified completion down 15%, or retries and re-dispatches down by a
  third.
- **Inconclusive (raise discrimination):** both arms complete at least 23 of 24.
- A shorter brief alone never qualifies.

**Experiment B** (B0 direct map and source reads; B1 an investigator Ticket), per question class:
- **Fail, whatever else:** a `NOT_FOUND` or "absent" claim outside a completely searched domain.
- **Adopt the helper for a class** only when supported-answer accuracy and the unsupported-claim rate are not worse,
  **and** the parent's context bytes or end-to-end latency fall by 25% while total cost, helper included, rises by at
  most 10%.
- Direct lookup stays the default for B-F1's class unless the helper is cheaper there.

**Experiment C** (C0 today's continuation; C1 with D1, and D5 where tested):
- **Blocks promotion:** any false completion claim, lost required work, or unauthorized duplicate effect, in any case.
- **Adopt** only when all six cases recover their required state, and repeated investigation in C-F5 falls, and the time
  to a verified continuation is not worse.
- A failure the baseline shares is recorded for its owner, never counted as a pass.

## Where E368's rewrite should use C1

E368 rewrites the worker packs as a core plus pointers, with an estimate of 36 to 42% less per run. C1 says to judge
that rewrite by what the worker achieves with it:
- **The false lines are truth fixes.** E368's corrections of what the texts say (the verifier's shell, the system
  text's "first message" line, the skills' contradictions) need no experiment: they are wrong today.
- **The size and selection change is a treatment.** Run it as Experiment A's A1 against today's pack as A0, worker,
  model, task and budget fixed, measured by verified completion, constraint preservation and additional source discovery.
  The bytes saved are a diagnostic, counted only when outcomes hold.
- **Until E389 runs,** E368's pull request can show delivery (before-and-after packs, E134's golden when it exists, and a
  scripted pass of the context-pack rehearsal) and should claim no effectiveness.
- **Two inputs for its design from R0:** the contract's knowledge list drops undelivered items silently (B7), so the
  pointers should name what is not delivered and why (D3); and the mandatory constraints stay in the core, never behind a
  pointer (plan §5.2, last paragraph).

R0 changes nothing else in E368's plan. The silent replacement pack (K2) is F36's, not E368's.
