# Handoff Prompt — Build the AEW Read-Only Dashboard in Parallel (v0.2)

You are the **parallel frontend implementer** for AEW (Agent Engineering Workflow).

Your task is to build a polished, read-only local dashboard while the main AEW line continues E5, ADR-0011, and M4. You are intentionally working ahead of the real backend adapter.

Read first:

- `aew-readonly-dashboard-design-v0.2.md` — governing design for your frontend work;
- current AEW docs needed to understand domain terminology;
- existing SPT/REVELATIONS frontend toolchain conventions if available.

## Authority boundary

You own frontend implementation under `web/**`.

Do **not** change AEW workflow semantics or depend on the current storage layout.

Do not modify unless specifically instructed:

- `src/aew/engine/**`
- `src/aew/history/**`
- control-state schemas
- E5 implementation
- ADR-0011 implementation

Do not parse `.aew` files in the browser.

Do not implement mutation routes or mutation controls.

The frontend displays backend conclusions. It does not decide gate legality, current/stale state, assurance, queue runnability, publication legality, required disposition, or authority.

## Build environment

Use the existing SPT Node 22 frontend toolchain/cache image. It already builds the full REVELATIONS UI without network access.

Relevant paths:

- `/opt/spt-frontend/npm-cache/`
- `/opt/spt-frontend/package/`
- `/opt/spt-frontend/frontend-npm-manifest.json`
- `/opt/spt-frontend/SHA256SUMS`

Create an AEW-specific `web/package.json` and lockfile using only the packages AEW actually consumes.

The frontend must build offline from empty `node_modules`.

## Work model

Build against a provisional `/api/v1` contract using:

- Zod schemas;
- MSW fixtures;
- React Query;
- React Router.

Treat DTOs in the design as provisional UI contracts, not AEW durable schemas. Centralize API access so later backend reconciliation is cheap.

## Product goal

This is not a rushed MVP. It is a non-blocking stretch project and can be integrated whenever ready.

Build the **core integration target first**:

- Overview;
- Attention;
- Work hierarchy/table/detail;
- Runs;
- Evidence;
- Knowledge/decisions;
- ADR-0011 history/integrity UX;
- M4 queue UX;
- explicit unknown/capability-unavailable/stale/mixed-revision states.

After D0–D4 is clean and frozen for integration, optional non-blocking work may add:

- bounded relationship/provenance graph;
- timeline;
- global read-only search / Cmd-K;
- metrics/observability;
- compare/diff views.

Do not let optional features or their dependencies delay the core frontend.

Use progressive disclosure and strong information density. Avoid generic admin-template and cyberpunk styling.

## First steps

1. Inspect the repo and confirm no existing `web/` conflict.
2. Inventory only the frontend packages you need from the shared cache.
3. Create the React/Vite/TypeScript skeleton.
4. Create Zod DTO schemas and MSW fixture worlds F0–F11 from the design.
5. Submit the DTO/contract file for the design's **C0 main-line review gate** before semantic shapes spread through page code.
6. Prove offline install/typecheck/lint/test/build inside the existing toolchain.
7. Build D1 onward in the design sequence.
8. Keep backend assumptions explicit and centralized.
9. Do not wait for E5/ADR-0011; mock missing capabilities.
10. Unknown backend enum values must render UNKNOWN, never as success/normal.
11. Capability absent means DATA UNAVAILABLE, never an empty/healthy result.
12. After a failed refresh, cached data must be visibly stale with age/revision.
13. Mixed control revisions must be visibly flagged.
14. Before declaring the core frontend integration-ready, run Playwright, the offline build gate, and the independent frontend review gate.

## Stop conditions / ask before crossing

Stop and ask rather than deciding if you believe you need to:

- alter AEW workflow semantics;
- add a write API;
- change a control-state schema;
- interpret ADR-0011 storage directly;
- modify E5 or Engine internals;
- define queue legality;
- define evidence/currentness semantics;
- define publication/assurance semantics.

Otherwise make normal frontend engineering decisions independently.

## Final deliverable

A frontend-complete branch/PR that:

- builds offline;
- passes frontend tests;
- runs fully against MSW;
- has no mutation controls;
- has no AEW storage coupling;
- centralizes API access;
- is ready to connect to the real read adapter later.


## Mandatory integration security/backend requirements

You do not implement these in Engine code, but your client and design assumptions must support them:

- the eventual local API session is authenticated with a mandatory high-entropy per-session token/session;
- loopback alone is not authentication;
- server validates Host and Origin;
- strict CSP blocks remote resources and record-authored beacons;
- remote Markdown images are disabled in V1;
- polled resources use ETag / If-None-Match and 304;
- normal polling is served from a revision-keyed derived projection cache and must not force a control lock/full parse per request;
- Overview should prefer one coherent backend snapshot projection;
- backend health is explicit data, never inferred by the frontend.

Do not weaken these requirements for convenience.

## Core independent-review requirement

MSW tests are not enough because they validate the frontend against data the frontend team invented.

Before D0–D4 is considered integration-ready, obtain an independent adversarial review covering:

- authority inference;
- unknown enums;
- capability absent;
- stale/disconnected data;
- mixed revisions;
- Markdown/XSS/external-resource behavior;
- dependency creep;
- no mutation surface;
- no storage coupling;
- DTO assumptions outside the centralized API layer.
