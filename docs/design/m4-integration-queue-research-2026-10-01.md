# Research: integration queues for M4 (mutating concurrency above 1)

- **Status:** research input for M4's plan, not governing. §7 records the designer's disposition (2026-10-01), which M4's plan adopts; §1 to §6 are unchanged.
- **Date:** 2026-10-01.
- **Feeds:** `future-work.md` F10 (integration queue and merge revalidation, M4), F3 (workspace strategy), E1 (`harness wait` on any of several runs) and D4 (deterministic integration checks). Also WC §8.1, §13 and §11.5's rule that "merge/conflict resolution and the integrated revision are new evidence-producing events; project policy determines which … checks, review findings, and verification steps must be rerun."
- **Builds on:** ADR-0004 (validate a merged candidate M = H + Ticket, then publish by `update-ref <branch> M H`; a moved ref makes the candidate stale, so rebuild and revalidate).

## 1. Summary

1. **ADR-0004 is already the core of a "not rocket science" queue.** The authoritative branch only ever moves to a commit validated exactly as published. M4's question isn't how to stay green, but **how much validation to redo, and when**, once several Tickets finish close together.
2. **Three designs exist in practice:**
   - **serial** (bors);
   - **speculative stacking** (Zuul's dependent pipelines, GitHub's merge queue);
   - **batching** (bors batches, merge-queue groups), plus SubmitQueue's conflict prediction on top.

   They differ in how much validation they waste when something fails.
3. **AEW's cost profile differs from CI's.** Post-integration verification is a model invocation, not just a build: dollars and minutes, and nondeterministic. Speculation that throws away verifier runs costs real money. Batching muddies per-Ticket provenance.
4. **Recommendation to evaluate:** M4 starts with a **serial integration queue over parallel implementation**:
   - Tickets implement, review and verify concurrently in their own workspaces;
   - only the integrate, post-integration-verify and publish tail is one-at-a-time, always on the current authoritative head.

   Measure queue wait before adding speculation. A deterministic integration-check path (D4) is the cheapest accelerator if waiting proves costly.

## 2. How the established designs work

| Design | Mechanism | On a failure | Source |
|---|---|---|---|
| **Serial** ("not rocket science", bors) | One candidate at a time: merge onto the current head, test, fast-forward. | Only that change is rejected. Nothing is wasted. | [S1] |
| **Speculative stacking** (Zuul dependent pipeline) | Each queued change is tested on top of every change ahead of it, all in parallel, "assuming that each change ahead … will pass". | Changes behind a failure discard their results and are retested without it. | [S2] |
| **Merge groups** (GitHub merge queue) | Each group holds a PR plus every PR ahead of it, built on the head of the group ahead. "Build concurrency" (1 to 100) caps parallel builds. | The failing PR leaves the queue and the groups behind it are rebuilt without it. | [S3] |
| **Conflict-aware speculation** (Uber SubmitQueue) | Predicts which pending changes may conflict ("touch the same logical parts of a repository") and speculates mainly along likely paths, using a build-graph analysis. | Bounded waste, at the cost of a predictor. | [S4] |
| **Batching** (bors batches; large merge groups) | Several changes validated as one merge. | Bisect to find the culprit. | [S1][S3] |

## 3. What is different about AEW

| Property | CI merge queues | AEW |
|---|---|---|
| Validation cost | Machine minutes | A post-integration **verifier invocation**: model tokens and minutes, plus deterministic checks. The M3 dogfood's T1 verifier cost USD 0.0025, cheap for small work but growing with scope. |
| Determinism | Mostly deterministic | Verifier verdicts are not. A re-verification can disagree with the first. |
| Evidence binding | A green status on a SHA | Evidence bound to an evaluated snapshot and fingerprint (ADR-0002), a plan revision and a candidate (ADR-0004 B1). A rebuilt candidate needs **new** evidence: the old one is bound to a different snapshot. |
| Unit of record | A PR | A Ticket, with its own completion record and provenance (WC §9.11). |
| Semantic conflicts | Caught only by tests | The isolation design §14.1: separate workspaces don't prove independence. The integration-stage check on the merged state is where cross-Ticket conflicts surface. |
| Dependencies | Usually none | Ticket dependency edges: a downstream mutating Ticket needs the upstream DONE and its M as an ancestor of its own base (ADR-0004). |

Consequences:
- **Speculation's waste is model spend.** In a stack of k, a failure at position i throws away k − i verifier runs. CI accepts that because machines are cheap; AEW should only accept it if queue wait costs more.
- **Batching weakens provenance.** One verification of {T1, T2, T3} would have to count as each Ticket's post-integration evidence, and a failure must be attributed by bisection, which means more verifier runs. It probably needs a Workflow Contract reading or amendment: can one integration evidence record serve several Tickets?
- **Serial always verifies on the true head.** Every candidate is verified on top of everything published before it, which is exactly where §14.1's semantic conflicts appear. Speculation also achieves that, but only once the stack ahead has passed.

## 4. Options for M4

### Option A (recommended to evaluate first): a serial integration tail, parallel everything else

- **Concurrent:** implementation, review and verification at Ticket scope, each in its own workspace. This is where most of the time goes.
- **Serial:** `prepare` → post-integration verification → publish, for one Ticket at a time, always on the current H. A Ticket reaching COMMIT_READY joins the queue.
- **A stale candidate stops being a surprise.** In a queue, a third-party move of the ref is the only remaining source of staleness. Today ADR-0004 handles staleness by rebuild and revalidate, which stays.
- **Queue order:** Lead-chosen, defaulting to FIFO by COMMIT_READY time. Dependency edges come first (an upstream Ticket is ahead of its dependants).
- **What's new to build:**
  - a queue record in control state: entry, position, status;
  - head-of-queue `prepare` that refuses out of order;
  - the scheduler's or Lead's view of the queue (`status`, `resume` next actions);
  - E1, so the Lead waits on whichever run finishes;
  - lifting the concurrency cap from 1 to N on live mutating workspaces (the cap counts live workspaces today).
- **Cost:** no wasted verification. Throughput is bounded by the post-integration verification time per Ticket.

### Option B: speculative stacking of depth k

- Candidate i is built on H + c₁ … cᵢ₋₁, and all are verified in parallel. Publishing goes in order by chained compare-and-swap: c₁ by `H→M₁`, c₂ by `M₁→M₂`, and so on.
- **Binding change:** a candidate's binding must include its **base chain**. A failure upstream retires every candidate built on it, with the same mechanics as today's `superseded` retirement.
- **When it pays:** queue wait dominates and verification failures are rare. Choose k by measurement.
- **Adds:** chained bases in candidate bindings; retirement cascades; the verifier dispatch policy for speculative candidates.

### Option C: batching

- One candidate for several Tickets, one verification. Each Ticket's completion record cites the shared evidence.
- **Needs a contract decision first:** whether shared post-integration evidence is acceptable provenance, and how a failure is attributed (bisection costs further verifier runs).
- Probably not for M4.

### Accelerator, independent of the option: deterministic integration checks (D4)

- Policy can let integration-scope verification run the project's deterministic checks only, with no model, for low-risk classes, under WC §11.5's "project policy determines what must be rerun".
- That makes revalidation cheap, which is the precondition for Option B ever being worth it.
- D4 is currently `On measured need`. M4's measurements decide it.

## 5. What M4 should measure (with the instrumented command log)

- **Queue wait:** time from COMMIT_READY to the start of integration, per Ticket, at concurrency 1, 2 and 4.
- **Integration tail time:** `prepare`, post-integration verification and publish, separately.
- **Rebuild rate:** how often a candidate goes stale or conflicts, and why (third-party move, dependency, real conflict).
- **Post-integration verdicts that differ from Ticket-scope verdicts:** the §14.1 semantic-conflict signal.
- **Lead cost per integrated Ticket:** O4 already shows the Lead at about 40% of cost. Queue choreography must not grow it; F15's stage commands are the counter.

## 6. Questions for the designer

1. Option A for M4, with B deferred until measured: agreed?
2. Queue order: FIFO by COMMIT_READY, dependency-first, Lead-reorderable? Can the Lead pull a Ticket out of the queue without leaving COMMIT_READY?
3. Can one post-integration evidence record serve several Tickets (Option C)? If never, say so in the contract.
4. D4: should M4 include the deterministic integration-check path, or wait for measurement?
5. With concurrency above 1, does a merge conflict at `prepare` return the Ticket to its implementer (a new attempt on the new head), or to the Lead for decision?

## 7. Designer's disposition (2026-10-01)

Recorded as given:

> M4 uses parallel Ticket execution with a single serial integration lease. Runnable COMMIT_READY entries default FIFO; dependency legality remains owned by the work graph, and the Lead may explicitly reorder or defer queue entries. M4 does not batch Tickets or share post-integration evidence. It implements a policy-selectable deterministic integration-validation path but retains existing verifier policy until evaluation supports cheaper routing. Merge conflicts release the integration lease and return to Lead disposition; AEW never automatically resolves them or sends them directly to an Implementer. Independent runnable entries continue rather than being head-of-line blocked. Every actual integration attempt recomputes the current dispatch predicate and binds to the current authoritative head.

How it answers §6:

1. **Option A**, as a single serial integration lease over parallel Ticket execution. Option B is not in M4.
2. **Order:** runnable entries are FIFO by default. The work graph, not the queue, decides dependency legality. The Lead may explicitly reorder or defer an entry.
3. **No batching** and no shared post-integration evidence in M4. This is M4's scope; it does not amend the contract.
4. **D4 is in M4** as a policy-selectable deterministic integration-validation path. Existing verifier policy stays the default until evaluation supports cheaper routing.
5. **A merge conflict** releases the lease and returns the Ticket to the Lead for disposition. AEW never resolves a conflict automatically and never sends it straight to an Implementer.

Two changes to Option A as written in §4:

- **No head-of-line blocking.** An entry that cannot proceed (deferred, or awaiting disposition) does not hold up independent runnable entries; the lease goes to the next runnable one. This replaces "head-of-queue `prepare` that refuses out of order".
- **Every integration attempt recomputes the dispatch predicate** (`DispatchDecision`, M4's first step) and binds to the current authoritative head. Queue position never carries a stale ALLOW.

The details belong to M4's ambiguity report: the lease's record and its owner, release on a crashed or lost holder, a third-party move of the ref while the lease is held, the queue states for deferred and awaiting-disposition entries, and which Ticket-scope evidence a new attempt after a conflict reruns (WC §11.5).

## Sources

Retrieved 2026-10-01.

- S1: [bors-ng](https://github.com/bors-ng/bors-ng), after Graydon Hoare's "not rocket science rule".
- S2: [Zuul, Project Gating](https://zuul-ci.org/docs/zuul/latest/gating.html)
- S3: [GitHub Docs, Managing a merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- S4: Ananthanarayanan et al., [Keeping Master Green at Scale](https://dl.acm.org/doi/pdf/10.1145/3302424.3303970), EuroSys 2019 (Uber SubmitQueue).
- In the repo: ADR-0002, ADR-0004, WC v0.7 §8.1, §11.5, §13, §21.1, `m1-implementation-plan.md` §4.7, `execution-workspace-and-isolation-design-v0.1.md` §14, `future-work.md` F3, F10, E1, D4, O4.
