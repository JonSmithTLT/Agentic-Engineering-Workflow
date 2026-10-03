# W02: main-line review

**Reviewed:** source freeze `0e64b31` on `feat/aew-dashboard-w02`, against `main` at `2e0bf40` (PR #26). The later commits up to `b9c233a` touch only `web/docs`.
**Reviewer:** main AEW line, 2026-10-03.
**Disposition: AMEND.** One finding (W02-1, Medium). Fix it inside W02; the rest is accepted as described in the packet.

## What was reviewed

I read the whole source diff (`web/src`, 2,870 lines) and the contract, and compared every vocabulary and route the new code relies on against contract 0.1.2:

- `api/transport.ts` and `client/queries.ts`: the 401/403 eviction, and polling only while a pane is displayed;
- `api/navigation.ts`, `api/links.ts`, `EntityAnchor`, `JumpToId` and `CopyDashboardLink`: the allowlisted parameters, workspace links and the clipboard fallback;
- `client/investigation-model.ts`, `Investigation.tsx` and `InvestigationWorkspace.tsx`: the Why explanations, the source and browser strips, and the inspector, drawer and focus handling;
- `RelationsExplorer.tsx`, replacing `LineageGraph`'s own graph;
- the page changes (Work, Runs, Overview, Attention, History);
- the `web.yml` change, and the one changed existing test (`developer-tools.test.tsx`: its 24-node bound and no-crawl assertions are kept).

**Not rerun here.** This machine has no Node, and no Docker in WSL, so the offline gate and the browser checks are the implementer's evidence only. The independent run will be the PR's CI on GitHub: the `web` job now runs `browser-w02.mjs`, and `assurance` requires it.

## Finding

### W02-1 (Medium): the relations explorer looks up Work references only in History

- **Where:** `client/investigation-model.ts:60-66` (`historyTargetKind`), used by `RelationsExplorer`.
- **The defect.** A History record's `depends_on` and `moved_to` links name **Work IDs**. Those units may still be current work: a moved unit's new parent is usually open. `historyTargetKind` makes them `history` nodes, so:
  - the anchor offers only `/history/{id}`;
  - **Expand** reads `/history/{id}`.

  For a unit that is still hot, that read is a 404. AEW's `history show` says so explicitly: "it is current work". The node then shows "Not found (404)" for a unit that exists.
- **Not new in W02, but wider now.** The classification came from the optional tools' `LineageGraph`, which I accepted on 2026-10-03 without catching it. W02 makes this explorer the shared provenance view for every inspector.
- **The History page already gets it right.** `HistoricalTarget` offers both Work and History lookups, as the core review accepted. The packet's "History links distinguish current lookups from archived source" holds for that page, but not for the explorer.
- **Fix:**
  - Classify `depends_on` and `moved_to` targets as `work`. The contract's `/work/{id}` is "Hot or archived work projection. Archived-by-ID includes later moves", so it resolves both.
  - Keep `audit_finding` as `history`: its target is an audit record, which exists only in history.
  - Keep the existing note that Work destinations are current projections, not historical snapshots.
- **Test:** a History record whose `moved_to` names a hot parent, which expands through `/work/{id}` (no `/history/` read for it), and whose anchor opens the Work workspace.

## Checked and sound

- **Contract alignment.** Every new known-value list matches contract 0.1.2: Work states, integration status (`prepared`, `publishing`, `conflict`, `superseded`), Health (`HEALTHY`, `DEGRADED`, `UNHEALTHY`, `UNKNOWN`), Capability (`AVAILABLE`, `UNAVAILABLE`, `UNSUPPORTED`, `UNKNOWN`), trust sources and invocation/harness statuses. Knowledge state, integrity status and Attention severity have no list, so their raw values warn, as the packet says.
- **Reasons.** Record-level reasons are always labelled unbound. Only Health and Capability, whose reasons sit on the same object as the status, are shown as bound. Codes stay opaque, and `blocked_by`, `findings` and `deviations` stay named sections.
- **Access refusal.** A 401 or 403 evicts that query's cached representation and validator (unless its session is already retired), and the page hides its payload. Ordinary failures keep last-known-good content, marked stale.
- **Concealed panes.** A hidden phone pane neither fetches nor polls, and refetches when it is shown again.
- **Session reset.** Explorer expansions check `context.retired` and abort on unmount, so an old expansion cannot repopulate a remounted graph.
- **Links.**
  - Only allowlisted parameters travel: demo keys in demo mode, plus filters, presentation and history keys in workspace and copied links.
  - A malformed `selected`, an unknown `inspector` or `field`, or a historical parameter (`rev`, `revision`, `snapshot`) stops before any request, with a stated reason.
  - `entityLink` now uses `Object.hasOwn`, so prototype keys never resolve to a route.
- **Bounds.** Three levels, 24 nodes, 80 edges, 100-row relation pages. Omissions are counted and shown, and no completeness is claimed.
- **CI.** `web.yml` keeps its triggers (`workflow_call` and `workflow_dispatch`), stable job names, permissions and change detection. It adds the W02 browser run and its failure-evidence directory. Nothing on the main line changes (`ci.yml`, CodeQL, Python).

## Acceptance

Fix W02-1 with its test in W02, then send the fixing diff. Once it is fixed and the PR's CI is green (web checks included), W02's frontend behaviour is accepted. That acceptance covers fixtures only. Live integration stays with F20.2 to F20.6.

## Fix confirmation (W02-1) — 2026-10-03

Reviewed `git diff b9c233a 7a18fa3` (one commit, five files; read from the shared repository). **W02-1 is fixed.**

- `historyTargetKind` classifies `depends_on` and `moved_to` as `work` and keeps `audit_finding` as `history`. Its one caller, `investigate`, feeds both the explorer's nodes and its edge list, so expansion now reads `/work/{id}`.
- `EntityAnchor` gets a `workWorkspace` flag, set only by `RelationsExplorer`. A Work node opens `/work?selected={id}`. From outside the Work collection, the link carries only `navigationParams` (demo keys), so History and Runs filters and selections don't leak into Work. Inside the Work collection, behaviour is unchanged. Other anchors are unaffected.
- **Tests:**
  - The component test `w02-investigation.test.tsx` expands a hot `depends_on` and a hot `moved_to` target. It asserts that both read through `/api/v1/work/`, that neither reads `/history/`, that there is no 404, that `audit_finding` stays `history`, and that the History filters (`kind`, `cursor`) are dropped from the parent link.
  - The browser check `browser-w02.mjs` covers the same flow on fixture F3 in demo mode, where `fixture=F3` is kept.
- No contract, dependency or workflow change.

Not rerun here, for the same reason as above. **W02's frontend behaviour is accepted once the PR's CI is green**, with the fixtures-only scope stated under Acceptance.
