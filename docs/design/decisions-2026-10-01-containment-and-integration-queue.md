# Designer decisions of 2026-10-01: containment, process ownership and the integration queue

**Status:** Decision record, governing. These decisions were given by the designer on 2026-10-01 and first recorded
inside the two research documents they answer: [`containment-and-process-ownership-rocky8-research-2026-10-01.md`](../research/containment-and-process-ownership-rocky8-research-2026-10-01.md) §8
and [`m4-integration-queue-research-2026-10-01.md`](../research/m4-integration-queue-research-2026-10-01.md) §7 and §7.1.
They are copied here verbatim on 2026-10-05 so that every governing decision lives in `docs/design/`, as the
amendment index design requires (ledger SAI-12, SAI-15) and the architecture review response accepted (G6: "keep research
documents out of the governing chain by copying accepted decisions into the proper decision/ADR records"). The research
documents keep their text as the record of what was asked and why; this document is what governs. Where the two
differ, this document wins.

**What depends on them:** register items F2 and E13 (closed, built in M4-B), Q3 (closed), the F2 scratch rule used by Q7
and F19, F10 and D4 (M4-D); ADR-0009's M4-B amendment; `m4-ambiguity-report.md` §2.4 and §2.6 to §2.9.

## 1. Containment and process ownership (Q3, F2, E13; research §8)

Recorded as given:

> **Q3 / F2:** Strong OS/runtime filesystem containment is required before any personal real-repository dogfood as well as internal alpha. The proposed unprivileged bubblewrap boundary is sufficient for personal dogfood once the Rocky 8 containment, OpenCode/bridge, Git-layout, fingerprint/prepare, fail-closed launch, and process-ownership probes pass. Internal alpha additionally requires representative isolation performance/operability acceptance.
>
> **E13:** Close POSIX process ownership through the same bubblewrap PID-namespace boundary. Do not implement a separate subreaper unless a pre-F2 Linux evaluation has a demonstrated need for reliable stop. Until the PID-namespace test passes, Linux process-group mode must not be represented as complete process ownership.

These answer the research's §7 questions 1 and 2. The probes the decision names map to the research's §6: containment
(§6 items 1, 2 and 6), OpenCode and the bridge (item 4), the Git layout and fingerprint/`prepare` (item 5), fail-closed
launch (§5), and process ownership (items 2 and 3). The research's questions 3 to 5 (agents' git write commands, read-only
reviewer and verifier workspaces, network containment) were settled afterwards as built in M4-B (ADR-0009, amendment of
2026-10-03: agents run no git write commands, reviewers and verifiers get read-only source) and by the network
containment design v0.2 (register F28).

Follow-up decisions, recorded as given:

> **Q7 classification:** Real-project provenance does not by itself trigger F2. A sanitized/disposable SPT-derived fixture counts as scratch only when the execution environment also has no writable non-disposable project state or secrets within the run's host-level reach. A disposable clone on the normal development host does not count as scratch. F19 follows the same rule.
>
> **F2 scheduling:** Move F2 from an unscheduled gate to early M4 / before first normal-host Q7 or real-repository dogfood. Run the Rocky 8 bubblewrap feasibility probes immediately, in parallel with other pre-M4 work. Implement F2 and E13 together if those probes succeed.

## 2. The integration queue (F10, D4; research §7)

Recorded as given:

> M4 uses parallel Ticket execution with a single serial integration lease. Runnable COMMIT_READY entries default FIFO; dependency legality remains owned by the work graph, and the Lead may explicitly reorder or defer queue entries. M4 does not batch Tickets or share post-integration evidence. It implements a policy-selectable deterministic integration-validation path but retains existing verifier policy until evaluation supports cheaper routing. Merge conflicts release the integration lease and return to Lead disposition; AEW never automatically resolves them or sends them directly to an Implementer. Independent runnable entries continue rather than being head-of-line blocked. Every actual integration attempt recomputes the current dispatch predicate and binds to the current authoritative head.

How it answers the research's §6:

1. **Option A**, as a single serial integration lease over parallel Ticket execution. Option B is not in M4.
2. **Order:** runnable entries are FIFO by default. The work graph, not the queue, decides dependency legality. The Lead may explicitly reorder or defer an entry.
3. **No batching** and no shared post-integration evidence in M4. Out of scope for M4, not forbidden by the contract (§2.1).
4. **D4 is in M4** as a policy-selectable deterministic integration-validation path. Existing verifier policy stays the default until evaluation supports cheaper routing.
5. **A merge conflict** releases the lease and returns the Ticket to the Lead for disposition. AEW never resolves a conflict automatically and never sends it straight to an Implementer.

Two changes to Option A as the research wrote it in its §4:

- **No head-of-line blocking.** An entry that cannot proceed (deferred, or awaiting disposition) does not hold up independent runnable entries; the lease goes to the next runnable one. This replaces "head-of-queue `prepare` that refuses out of order".
- **Every integration attempt recomputes the dispatch predicate** (`DispatchDecision`, M4's first step) and binds to the current authoritative head. Queue position never carries a stale ALLOW.

### 2.1 Follow-up dispositions (designer, 2026-10-01; research §7.1)

The implementer asked about five details the disposition left open. Recorded as given:

> **Lease:** owned durably by the queue entry, with an active invocation as custodian. A dead custodian is reconciled before transfer/release. No timeout alone releases a load-bearing lease. Publishing ambiguity always goes through ADR-0004 reconcile.
>
> **Head movement:** one automatic rebuild + revalidation on the new authoritative H is allowed while retaining the lease, only after proving no publication occurred and recomputing current dispatch legality. A second movement, conflict, failed validation, or changed legality returns to Lead disposition.
>
> **Queue states:** DEFERRED and AWAITING_DISPOSITION are queue/scheduling states. The Ticket may remain COMMIT_READY. Queue state never grants workflow eligibility.
>
> **Conflict evidence:** actual conflict resolution creates a new implementation attempt / fingerprint. Snapshot-bound checks, review and verification do not carry forward automatically; rerun the effective gates for the Ticket's class/policy. Plan/assurance is recomputed from its bindings. Every new integration candidate receives new integration validation. A simple authoritative-head move does not by itself invalidate unchanged Ticket-scope evidence.
>
> **Batching:** out of scope for M4, not forbidden by contract.

**Revised in the designer's review of this record (2026-10-01):** the durable lease owner is the queue entry, not the replaceable integration candidate or attempt, as first given. A rebuild or a new attempt replaces the candidate under the same lease.

M4's ambiguity report turns these into records, transitions and tests (§2.6 to §2.9); the remote integration target sketch (register F23, Q14) names what the queue's records must not foreclose.
