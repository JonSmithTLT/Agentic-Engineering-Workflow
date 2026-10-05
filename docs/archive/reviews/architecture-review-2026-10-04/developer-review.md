# Developer review of the architecture review response (Q13)

- **Date:** 2026-10-04
- **Reviewer:** the lead developer.
- **Reviewed:**
  - `docs/design/architecture-review-response-2026-10-04.md`, the proposed disposition;
  - `REVIEW.md` (archived as `docs/archive/reviews/architecture-review-2026-10-04.md`);
  - the review's ADR-0012 outbox draft in this folder.
- **Code basis:** `main` after M4-B, plus the Lead custody branch (`fix/lead-custody`, PR #40). That branch moves credential delivery into the CLI layer, which matters for question 10.
- **Disposition requested by §15:** see the summary.

## Summary: CONCUR WITH MODIFICATION

The response is right about which foundations are stable (§11) and about keeping `REVIEW.md` an input rather than a roadmap. I concur with G1, G3, G6, G8, G9, the K items and §14 as written.

Five modifications, each tied to a code seam or a recovery property:

1. **The outbox must not cap events where a consumer needs them** (G11 and K2, against ADR-0012 draft D2). The cap is right for the hot state, but the draft's escape hatch doesn't exist (questions 2 and 4).
2. **The first typed-surface transport should be the CLI relay through the Lead broker, not MCP** (G2, question 10). Custody now lives on that path.
3. **Commit invariants belong in the store's commit, not in transaction finalizers.** The outbox draft and the dispatch review reached this conclusion independently (question 1).
4. **Ship the outbox in two steps.** M4-D needs the wake signal and the completeness guarantee for wait-any. Typed events, sealing and the chain wait for the first consumer that reads them (questions 5 and 6).
5. **A knowledge service identity is a new credential kind and a new row in ADR-0009's environment-trust inventory**, not just "a bounded subject" (K4, question 3).

## Answers to §15

### 1. Hidden implementation coupling
- **Finalizers are not the commit path.** `Kernel.lead_txn` runs the transaction finalizers. Five sites commit through `Session.commit` directly and run none: `lead.acquire`, `lead.handoff.accept`, `lead.takeover`, `harness.{stop,send,interrupt}`, and `migrate` (which runs them by hand). This bites twice:
  - the outbox draft moves event derivation into `ControlStore._commit` for this reason;
  - the dispatch review (area 3, note 1) found that "no invocation without a decision" holds only by convention for the same reason.

  **Proposal:** make `Session.commit` the one place commit-time invariants run: the dispatch admission check, the outbox events, and any future rule. Finalizers stay for work that needs a transaction context. The dispatch fix (D4, on `fix/dispatch-legality`) puts the no-undecided-invocation check there now; the outbox should use the same seam, not a second one.
- **The typed surface reaches lower than "transport adapters".** The CLI layer now does real work beyond argument parsing:
  - `--fields` turns free text into data with no shell involved;
  - credential delivery is terminal-only (`cli/credentials.py`), with its pre-issue refusal;
  - `lead_broker.refuses_locally` refuses credential-issuing commands in a Lead session;
  - the engine is entered through `dispatch.channel("cli")`.

  A second transport must reproduce each of these or get them from a shared layer. Credential-issuing operations especially must never be callable through a typed transport that returns their result to a model (see 10). Put this in D-AR2's scope.
- **The dashboard's event endpoint needs a server process with a position.** That is Q12 (who owns long-lived processes), so G11's dashboard consumer and G8 are coupled. The response sequences both in M4-D/E, which is consistent. Name the dependency in D-AR3.

### 2. State growth
- **Outbox (ADR-0012 draft D2):**
  - The 64-event cap keeps `last_transition` constant in history. That is right, and the hot state must stay bounded.
  - **But the draft's escape hatch doesn't exist.** It says "a consumer that needs the rest diffs the two states". Old states are not retained: `control.yaml` is overwritten, and a log record holds the transaction's write hashes, not prior state content. So a truncated transition (the one-transaction migration of 3,000 units, an Epic cancel cascade) loses its events for every consumer.
  - The capture worker's job identity `(revision, event_index)` then has no event behind index 64.
  - **Modification:**
    - write the full event list to an immutable staged file, `state/log/<rev>.events.yaml`, as a redo-staged write inside the commit point;
    - keep in `last_transition` only `{count, sha256, first_n}`;
    - make the log record carry the file's hash.

    Hot state stays bounded and the commit stays atomic. Consumers lose nothing, and the history-independence property is unchanged, because the file is written once and never read on the commit path.
- **Cost ledger (G7):** per-run usage must go to the run record and the cold history at archival, never into hot `invocations[*]` past the run's end. A roll-up per Ticket is a derived view, rebuilt from history like `local/history.sqlite`.
- **Evaluation (G1):** run records live outside `.aew/` (the F19 rule already puts hidden material in the private repository). Nothing in evaluation should write project control state.
- **Knowledge dispositions and receipts:** cold by construction if they are history entries (see 9). The capture queue must not live in `control.yaml`.

### 3. Authority seams
- **The typed action surface is a seam only if it calls something other than the engine API.** Rule: every transport calls `Engine` methods under `dispatch.channel(<transport>)`, so dispatch decisions record which transport made them. Then no second mutation path exists. Add a conformance test: a transport adapter must not import `aew.engine.store`.
- **Outbox consumers are readers.** The draft's "readers take no control lock" is right. A consumer that must act, such as the scheduler, acts through the same typed surface with its own credential, never by writing state.
- **The knowledge service identity:**
  - Today the verifier knows two credential kinds, Lead and invocation, and custody is argued per kind in ADR-0009's amendment. A third kind needs:
    - its own row in the environment-trust inventory;
    - its own scrubbed variable in `contract.CREDENTIAL_ENV`;
    - a holder process with the same custody as the broker: non-dumpable on Linux, never in an agent's environment;
    - a statement of what takeover does to it.
  - The response is right not to assume takeover revokes it. I'd decide it now, though: bind it to the project and the operator, not the Lead generation. Otherwise every takeover silently breaks capture.

### 4. Failure and recovery
For the crash points across commit, outbox consumption, capture, indexing and delivery:

| Crash point | Recovery |
|---|---|
| between commit and the log file | repaired at the next lock (the draft's probe 2) |
| between commit and wake | latency only |
| consumer after processing, before the cursor advances | redelivery; idempotence by `(revision, event_index)` |
| capture after admission, before its receipt | admission must be idempotent by the same key (capture §8 says so) |
| indexing (FTS) | derived, rebuilt |

That is coherent **only if event identity is stable and complete**, which the cap breaks (point 2). With the staged events file, all five are recoverable.

One gap: the response doesn't say what happens to a consumer whose cursor points into a sealed segment while sealing is pruning. The draft takes the lock for the prune, which is fine, but add the read-during-prune case to D-AR3's tests (the draft lists it under integration; keep it).

### 5. Sequencing
- **Truly blocking approved M4 work:**
  - the outbox's wake signal plus the completeness guarantee, for M4-D's wait-any.

  Nothing else in the response blocks M4-C. I1 and I2 (the containment corrections) were already built in M4-B.
- **Should stay later even though attractive:**
  - **typed events beyond what wait-any reads.** Wait-any needs only the wake signal and the run records (draft D5). Events matter to the dashboard push and to capture, neither of which is in M4-D;
  - **sealing, until measured.** 60,000 files is about 3,000 Tickets; the dogfood projects are two orders below that;
  - **the record chain (draft D7)**, until an audit requirement names it;
  - **SSE for the dashboard** (I12).

  This splits D-AR3 into "wake and completeness" (M4-D) and "events, sealing, chain" (with the first consumer).

### 6. Complexity
- **Solving problems we don't have yet:**
  - multi-scope visibility (already deferred: good);
  - the outbox chain;
  - log sealing;
  - OpenTelemetry (already deferred);
  - the minimal skill-delivery path, unless F19 shows skills help.
- **The cost ledger is borderline.** It has a real consumer (F19 comparisons) only once F19 exists, so build it with D-AR1, not before.

### 7. Reuse
- **Wake:** the supervisor already does an identity stat of `control.yaml` each tick (`base._authority_files_identity`). The wake file is the same idea, and no new subsystem is needed.
- **Admitted-knowledge integrity:** extend the ADR-0011 history manifest with new entry kinds rather than a sibling manifest. That gives one audit fold, one chain and one `history audit`. The manifest's audit cost grows with entry count, and admitted knowledge is low-volume (curated records, not capture jobs). Operational capture state stays outside the manifest, as the response says.
- **The knowledge service credential:** reuse the credential verifier and the broker's custody pattern (a holder process, a bridge, terminal-only issuance). It needs a new kind, not a new mechanism.
- **FTS:** on `local/history.sqlite`, which is already derived and rebuildable.

### 8. Testability
Yes, for every shared primitive, without a real provider:
- **outbox:** the store model asserts event fidelity per commit (draft rule 25), the crash matrix covers the new fault points, and a two-process wake test measures latency;
- **typed surface:** a conformance test runs one scenario through each transport and compares the engine-side results and the dispatch decisions' channels;
- **knowledge identity:** the custody tests of PR #40, extended to the new kind (environment scrubbing, non-dumpable holder, refusal outside its operations);
- **evaluation component:** fixture and run-record schema tests, plus a fake-harness end-to-end run.

### 9. Knowledge implementation
The split is practical and coherent, with one sharpening. The boundary is "is it needed to reconstruct or audit what was admitted and why". If so, it goes to the history domain; if not, it's operational.
- **Capture job states, retries and cursors:** operational, but the cursor must be durable outside `local/` (the draft's D8 says so), or a deleted `local/` would replay the whole log into capture. Idempotence makes that safe but potentially expensive.
- **Receipts that record why a candidate was rejected:** audit material, so history entries.

### 10. Typed surface: is MCP the right first adapter?
**No. Implement the typed service contract behind the CLI relay first, then MCP once spiked.**
- **The relay already exists and already carries custody.**
  - In a Lead session, `aew` commands go to the Lead broker, which holds the credential and relays argv to the engine.
  - Since PR #40, credential-issuing commands are refused there, and credentials go only to the operator's terminal.
  - A JSON-in (`--fields -`), `ActionProjection`-out (`--json`) contract on that path removes the shell quoting and YAML failure classes the review measured, with no new process and no new credential holder.
- **An MCP server would be a new long-lived process acting for the Lead.** Either it holds the Lead credential (a second holder, so a new custody argument) or it relays to the broker (then it is a transport over the relay, and the relay comes first anyway).
- **MCP's runtime behaviour is unverified.** We haven't verified MCP behaviour on OpenCode 2.0.18 in the air-gapped configuration: tool listing, progressive disclosure, error shapes, timeouts. That's a probe, as the response says for G4.
- **Order:**
  1. D-AR2 defines the typed actions and `ActionProjection`;
  2. the CLI relay implements them;
  3. MCP becomes a thin adapter over the same calls after the probe.

  The semantics are the same either way. Only the first transport changes.

## Smaller points
- **G2, mechanical retry:** list the retryable actions in `PrimitiveSpec`, not in each transport, so the rule can't diverge.
- **I5 (pin acceptance inputs) is the same mechanism as the dispatch review's D1** (decisions check the record and plan hashes control state pins). D1 is on `fix/dispatch-legality`; I5 extends it to repository-local acceptance inputs and can reuse the same check.
- **K6:** agree. The dashboard contract (0.1.x) should name the engine record each projection field comes from, so a frontend-preview field can't become a backend semantic by default.
- **§12 places I1 and I2 in "M4-B/C immediate corrections".** Both were built in M4-B (#36). The requirements ledger records them as done (ARR-13, ARR-14), so §12 can say so.
