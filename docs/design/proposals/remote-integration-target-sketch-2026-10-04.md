# T8 — Remote integration target: a sketch that stops at the adapter interface

- **Status:** sketch only, from the independent architecture review (thread T8 of `HANDOFF.md`; `REVIEW.md` G10, F-G), 2026-10-04. Classified **WAIT FOR DEPENDENCY** in `TRIAGE.md`: the designer's question 8 ("is a remote (PR) integration target in scope before internal alpha?") is open and M4-D's queue records are still being designed. This note exists so that the question can be answered with the shape in view, and so that M4-D does not foreclose it by accident.
- **Basis:** ADR-0004 (decision, amendment and addendum); `engine/integration_ops.py` (the saga: prepare → post-integration verification → publish by CAS → DONE; `OPEN_INTEGRATION`, `KEEPS_INTEGRATION`); WC §13 ("external Bitbucket/Jira/SCM state is recorded through identifiers/status adapters and remains a separate authority boundary"); ADR-0012 draft D5 (run status is not a committed fact; the Lead ingests).
- **Does not touch:** ADR-0004's publication point (the ref CAS) for the local target; M4-D's lease; T1's surface.

## 1. What changes and what does not

Today the authoritative branch is local: `publish` moves `refs/heads/<branch>` from H to M by compare-and-swap, syncs the authoritative worktree, and marks the Ticket DONE in one locked transaction. The branch *is* the publication point and `DONE` means "M is on the authoritative lineage and post-integration verification passed on M".

With a remote target the publication point is **owned by someone else**: a pull request merged by the provider, often with a merge commit or squash that AEW did not compute, after checks AEW did not run. Three things follow, and they are the whole design problem:

1. `DONE` cannot be declared at publish; it is **observed**. The Ticket waits in a new integration status until the provider reports the merge, and the merged commit M' may differ from the candidate M.
2. The candidate's **base** H is the remote branch's head at prepare time, and it moves without AEW's CAS; "stale candidate" is detected by the provider's merge check, not by `update-ref`.
3. **Reconcile** cannot inspect only local git. It must ask the provider (or fetch and inspect the remote ref) and must tolerate a provider that is unreachable.

Everything else in ADR-0004 stays: prepare commits the workspace and merges onto H in a detached worktree; post-integration verification runs on M; the binding to the acceptance (`commit_ready_seq`, plan revision, gated fingerprint) is re-checked before any outward action; a retired candidate ends write authority.

## 2. `integration.target`

A project policy choice, in `policy/execution.yaml` or a new `policy/integration.yaml` (not decided):

```yaml
integration:
  target: local            # local | remote
  remote:
    provider: github       # an adapter name (registry like harness adapters: BUILTIN plus AEW_INTEGRATION_ADAPTERS)
    remote: origin
    branch: main           # the protected branch; AEW never pushes to it directly
    merge_method: observe  # AEW proposes; the provider merges (squash | merge | rebase are the provider's settings, recorded, not chosen here)
    poll_s: 60
```

`target: local` is today's behaviour, unchanged. `target: remote` changes the publish phase and adds a wait.

## 3. The saga with a remote target

| Phase | Local (ADR-0004) | Remote (sketch) |
|---|---|---|
| prepare | merge onto local H → candidate M in a detached worktree | fetch; H = remote branch head; merge onto H → M; **push M to a candidate ref** `refs/aew/candidates/<T>-<n>` on the remote (never to the protected branch) |
| post-integration verification | Verifier on snapshot(M) | unchanged (local M) |
| publish phase 1 | record `publishing {H → M}` | record `proposing {H → M}`; adapter `open(candidate_ref, base_branch, title, body)` → `{proposal_id, url}`; status `proposed` |
| publication point | `git update-ref` CAS under the lock | **the provider's merge**, outside AEW's authority |
| wait | none | `observing`: the Lead (or wait-any, ADR-0012 D8) polls `adapter.status(proposal_id)` → `open | merged {commit} | closed | conflict | checks_failed`; a new base head makes the candidate `stale_candidate` exactly as a moved ref does today |
| DONE | phase 2 in the same lock | on `merged {M'}`: fetch; verify M' contains M's tree (squash) or M itself (merge); record `integration.commit = M'`, `integration.proposal = {...}`; sync the authoritative worktree to M'; DONE with a Completion Record that names M' and the proposal |
| reconcile | inspect git: ref == H, ref contains M, else stale | inspect the provider **and** git: proposal merged and remote head contains M' → finish; proposal open → still `observing`; proposal closed → candidate retired `discarded` with the provider's reason; provider unreachable → stay `observing`, report `INTEGRATION_TARGET_UNREACHABLE` (a new reason code, registry-only) |

**What `DONE` means** under a remote target: "the provider merged a proposal built from candidate M, the resulting commit M' is on the protected branch, and AEW's post-integration verification passed on M". Whether verification must re-run on M' when M' ≠ M (squash, rebase, a merge with other work) is the one semantic question this sketch leaves to the designer (§5 Q2); the conservative answer is yes, as a second `integration` scope invocation, which the saga already knows how to run.

## 4. The provider adapter interface (sketch)

One adapter per provider, narrow like `HarnessAdapter`, holding **no AEW credential** and no provider token in AEW state (the token is the operator's, read from the environment the Lead launched with, as `provider_env` is today):

```python
class IntegrationTarget(ABC):
    name = ""
    def push_candidate(self, repo_root, candidate_ref, commit) -> None: ...
    def open(self, *, candidate_ref, base_branch, title, body, metadata) -> dict:   # {"proposal_id", "url"}
    def status(self, proposal_id) -> dict:   # {"state": "open|merged|closed|conflict|checks_failed", "merge_commit", "base_head", "checks": [...]}
    def close(self, proposal_id, reason) -> None: ...                               # on retirement
    def fetch(self, repo_root, branch) -> str: ...                                  # the remote head; a plain git fetch
```

`status` is the only read; it is polled, never streamed, so an unreachable provider degrades to a longer wait. Nothing the adapter returns is evidence: a merged state is confirmed by `fetch` and `merge-base --is-ancestor` before DONE, the same way ADR-0004's reconcile never infers success.

**Where it does not belong:** the harness adapter (a different boundary), the Lead broker (the operator's provider token must not become reachable from the Lead model's shell), the supervisor.

## 5. Questions for the designer (only two, both blocking for scope)

1. **Is it wanted before internal alpha?** (handoff question 8). If no, nothing here is built and M4-D proceeds with `target: local` as the only value; the record shapes in §3 (`proposing`, `observing`, `proposal`) cost nothing to reserve as status names so the schema does not foreclose them.
2. **Verification on M'.** When the provider's merge commit differs from the candidate, does `DONE` require a second post-integration verification on M', or is verification on M plus "M' contains M" enough? The conservative answer doubles verifier cost per remote integration; the permissive one trusts the provider's merge.

## 6. What M4-D should not foreclose

- The queue's lease (M4-D) should hold through `proposing` and `observing`, or release at `proposed` and re-acquire at merge; either works, but the records must allow a candidate to be open against a base that is **not** the local branch head.
- `integration.status` is an open string set today (`OPEN_INTEGRATION`); adding `proposed`, `observing` later is additive if nothing asserts the closed set.
- The Completion Record (WC §9.11) should have room for `integration.commit` ≠ the candidate commit.

## Not decided here

Provider choice (GitHub first is the obvious one given `gh` usage; Bitbucket is the WC's example); whether AEW ever merges through the provider's API itself (`merge_method: merge`) when the operator's token allows it, which would restore a CAS-like publication point (`sha` precondition on the merge call) and make `DONE` immediate again; how CI checks on the proposal relate to AEW's own post-integration verification (two sets of evidence with different trust labels).
