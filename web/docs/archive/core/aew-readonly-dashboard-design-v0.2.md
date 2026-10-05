# AEW Local Read-Only Dashboard — Parallel Frontend Design v0.2

**Status:** Proposed stretch-goal design for parallel implementation; incorporates independent design review\
**Date:** 2026-10-02\
**Audience:** second implementation LLM working independently of the main AEW line\
**Primary rule:** **One Engine owns meaning. The dashboard only renders read projections.**

## 1. Executive intent

Build a local, read-only web dashboard for AEW that can be developed largely in parallel with E5, ADR-0011, and M4.

It should answer without consuming Lead/model turns:

- What is AEW doing right now?
- What does AEW know about the work and why?
- What needs human attention?
- How are work, evidence, decisions, invocations, history, and integration state related?
- What changed recently?
- What durable knowledge exists and how is it connected?

This is not a throwaway MVP. Because the frontend is not blocking core AEW work and can be integrated whenever ready, the parallel frontend line may build a richer, polished workbench than a critical-path milestone would justify.

The frontend may proceed ahead of the backend using a frozen mock/DTO contract and MSW fixtures.

## 2. Architectural position

The dashboard is a **projection** of AEW state and knowledge, never an authority surface.

```text
                    AEW Engine
                        │
                read/query projections
                        │
                read-only HTTP adapter
                        │
          127.0.0.1:<ephemeral-port>
                        │
                 compiled SPA
                        │
                     browser
```

Forbidden:

```text
browser → control.yaml
browser → .aew/history/*
browser → history SQLite index
browser → manifest segments
browser → workflow/gate logic
```

The frontend must never implement or infer AEW authority semantics.

## 3. AEW state this design assumes

### 3.1 Current accepted baseline

M3 is accepted. AEW already has:

- Project → Epic → Story → Ticket hierarchy;
- mutating and non-mutating Tickets;
- plans and plan acceptance;
- evidence;
- review and verification;
- integration/publication state;
- durable decisions;
- Lead authority and generation;
- invocation and harness run records;
- deterministic gates/refusals;
- status/resume/work/invocation read surfaces;
- OpenCode integration;
- immutable evidence history.

### 3.2 Pre-M4 work currently underway

Before M4 begins:

1. **E5 / P1** replaces the Engine's implicit 12 `*Ops` mixins plus `EngineBase` composition with a Kernel and explicit collaborators while preserving public behavior.
2. **ADR-0011 / P2** introduces history-independent hot/cold state and first-class historical access.
3. **P3** validates ADR-0011 performance, migration, history access, and invariants.

Therefore the frontend must not depend on the current `control.yaml` schema, mixin MRO, or ADR-0011 storage layout.

### 3.3 Near-term capabilities the dashboard should be ready for

Capability-gated support should exist for:

- ADR-0011 history access and integrity status;
- M4 integration queue;
- E12 evidence viewing;
- F15-style action projection data: `mechanical_actions`, `decisions_required`, `blockers`, `anomalies`;
- future project maps / derived knowledge;
- future model/resource usage if exposed;
- future capability manifests.

The UI must still work when some capabilities are absent.

## 4. Non-negotiable boundaries

### 4.1 Read-only means read-only

No API or UI control may:

- create/revise work;
- accept/reject a plan;
- ingest/accept evidence;
- transition workflow state;
- launch/stop runs;
- classify/resolve findings;
- waive gates;
- reorder/defer queue entries;
- authorize publication;
- publish;
- edit history;
- edit project authority.

If write operations are ever added, that is a separate design and review.

### 4.2 The frontend never derives workflow truth

The backend owns conclusions such as:

- CURRENT / STALE;
- gate pass/fail;
- dispatchability;
- review/verification sufficiency;
- `requires_disposition`;
- publication legality;
- queue runnability;
- plan assurance;
- whether historical data is current evidence;
- contradictions.

The UI displays backend-provided values and reason codes.

### 4.3 No Engine/storage coupling

The second LLM should not modify unless explicitly coordinated:

```text
src/aew/engine/**
src/aew/history/**
control-state schemas
ADR-0011 implementation
E5 implementation
```

Normal frontend ownership:

```text
web/**
frontend fixtures/tests
frontend design docs
```

Python packaging/server integration is deferred to the integration phase.

## 5. Parallel implementation strategy

```text
MAIN AEW LINE                         PARALLEL DASHBOARD LINE

E5                                  Dashboard design
ADR-0011                            DTO/OpenAPI draft
M4 engine semantics                 MSW mock server
read/query projections              React application
read-only HTTP adapter              component + browser tests
        │                                  │
        └──────── versioned contract ──────┘
                           │
                       integration
```

The dashboard should be able to become **frontend-complete against mocks** before the real HTTP adapter exists.

### 5.1 Work that can start immediately

Core integration target:

- React/Vite/TypeScript project;
- shell and routing;
- visual system;
- Overview;
- Work explorer/detail;
- Runs;
- Evidence/Knowledge;
- History UX;
- Attention;
- Queue UX;
- loading/error/empty/degraded states;
- MSW fixtures;
- unit/component tests;
- Playwright smoke tests;
- offline production build.

Optional work may continue after the core frontend freezes for integration:

- bounded relationship/provenance graph;
- compare/diff;
- global search / Cmd-K;
- timeline explorer;
- metrics/observability.

The optional work is intentionally non-blocking and must not delay integration of a sound D0–D4 core.

### 5.2 Decisions the frontend worker must not make

Do not decide workflow, gate, evidence-currentness, assurance, queue-legality, publication, authority, or storage semantics. Model them as backend data.

## 6. Build and offline environment

Use the existing SPT frontend toolchain image.

### Existing builder

`images/frontend-node-toolchain/Dockerfile`

Already established by REVELATIONS:

- Node 22 on `bookworm-slim`;
- offline npm cache;
- package/lock material;
- frontend dependency manifest;
- checksums;
- full REVELATIONS site builds without networking.

Relevant image paths:

```text
/opt/spt-frontend/npm-cache/
/opt/spt-frontend/package/
/opt/spt-frontend/frontend-npm-manifest.json
/opt/spt-frontend/SHA256SUMS
```

The offline frontend ecosystem is considered proven. Do not re-investigate generic npm-cache feasibility.

### AEW frontend ownership

Create:

```text
web/
  package.json
  package-lock.json
  tsconfig.json
  vite.config.ts
  src/
  tests/
```

AEW declares only the subset it uses. Do not copy the giant SPT dependency-pack manifest.

### Offline build gate

From empty `node_modules`, networking disabled:

```text
npm ci --offline
npm run typecheck
npm run lint
npm run test
npm run build
```

Follow REVELATIONS' existing container invocation conventions where useful.

Node is build-time only. The deployed AEW runtime serves compiled HTML/CSS/JS.

## 7. Approved dependency subset

### Core

- `react`, `react-dom`, `react-router-dom`
- `typescript`, `vite`, `@vitejs/plugin-react`

### API/contracts

- `@tanstack/react-query`
- `openapi-fetch`
- `openapi-typescript` when the backend spec lands
- `zod`

### UI

- `tailwindcss`, `postcss`, `autoprefixer`
- `clsx`, `tailwind-merge`, `class-variance-authority`
- `lucide-react`
- selected Radix primitives only: tabs, tooltip, dialog, dropdown-menu, scroll-area, collapsible, separator, select, progress, popover

### Dense data

- `@tanstack/react-table`
- `@tanstack/react-virtual`
- `date-fns`

### Knowledge/evidence

- `react-markdown`, `remark-gfm`, `rehype-sanitize`
- `react-json-view-lite`
- `shiki` or `prismjs`

### Testing

- `vitest`
- `@testing-library/react`
- `@testing-library/jest-dom`
- `jsdom`
- `msw`
- Playwright only for the browser smoke lane

### Optional feature dependencies — add only when the feature begins

- graph: `@xyflow/react` plus **one** layout engine (`dagre` or `elkjs`);
- bounded client-side search: `fuse.js`;
- compare/diff: `react-diff-viewer-continued`;
- metrics: `recharts`.

### Available later, not part of the initial dependency review

D3/Sankey, Monaco, xterm, TipTap, export/PDF, DnD, geo packages.

**Dependency-budget rule:** the shared offline cache proves availability, not approval. Every direct AEW dependency must have a current feature using it. Optional-feature dependencies land in the PR that introduces that feature, not in D0 pre-emptively.

## 8. Product/visual direction

This is an **engineering operations and knowledge workbench**.

Do not make it a generic SaaS admin template, SOC/cyberpunk dashboard, KPI-card wall, or terminal replacement.

Priorities:

1. information density;
2. fast scanning;
3. strong hierarchy;
4. provenance on demand;
5. progressive disclosure;
6. clear attention states;
7. low visual noise;
8. keyboard-friendly navigation;
9. stable deep links.

Suggested shell:

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ AEW / <project>  Lead G17  rev 843  age 0.7s  health: backend=HEALTHY │
├─────────────────┬────────────────────────────────────────────────────────┤
│ Overview        │                                                        │
│ Attention       │                                                        │
│ Work            │                                                        │
│ Runs            │                       PAGE                             │
│ Evidence        │                                                        │
│ Knowledge       │                                                        │
│ History         │                                                        │
│ Queue*          │                                                        │
│ Graph           │                                                        │
│ Metrics*        │                                                        │
├─────────────────┤                                                        │
│ Search / Cmd-K  │                                                        │
└─────────────────┴────────────────────────────────────────────────────────┘
```

Support light/dark mode, defaulting to system preference. Never rely on color alone for state.


### 8.1 UI honesty rules

The dashboard must fail **openly**, never reassuringly.

1. **Unknown enum/state values render as unknown.**
   - Every semantic badge/style mapping has an explicit unknown branch.
   - Unknown values use a warning/unknown presentation and display the raw backend value.
   - Unknown values never inherit a green, success, neutral, or "normal" style by default.

2. **Capability absent means unavailable, not empty.**
   - If `attention=false`, the UI says `Attention data unavailable in this AEW version`, not `0 attention items`.
   - The same rule applies to history, queue, metrics, maps, search, and any future capability.
   - Unsupported values are not included in health calculations.

3. **Health is backend-supplied only.**
   - The frontend never infers "healthy" from HTTP 200s, empty lists, successful polling, or absence of visible errors.
   - A health indicator is shown only from a backend health field such as `HEALTHY | DEGRADED | UNHEALTHY | UNKNOWN`, plus backend reasons.

4. **Data age and revision are visible.**
   - Every response carries `generated_at` and `control_revision`.
   - The shell shows the newest successfully rendered revision and age.
   - When refresh fails, cached data may remain visible but the view becomes explicitly `STALE/DISCONNECTED` and shows the age since the last successful response.

5. **Mixed-revision views are explicit.**
   - A page that combines independently polled resources tracks all visible `control_revision` values.
   - If they differ, show `Updating — mixed revisions <min>…<max>` rather than presenting the page as a coherent snapshot.
   - Prefer a backend composite/snapshot endpoint for Overview/Attention/active-run summaries so the most important page is naturally coherent.

These rules get explicit tests; they are not visual polish.

## 9. Information architecture

### `/` — Overview

Answer **what matters right now?**

Show project/branch/revision, Lead generation, isolation labels, active-work counts, active runs, review/verify/integration counts, attention summary, history-audit summary, recent meaningful activity, and optional resource/cost summary.

### `/attention`

Sections:

- decisions required;
- blockers;
- required findings;
- anomalies;
- integrity/health warnings.

Each item links to its subject and shows backend reason codes. No resolution controls.

### `/work`

Switchable tree/table with filters for kind, state, mutating/non-mutating, parent, classification, assurance, attention, and current/historical where meaningful.

Virtualize/paginate large data.

### `/work/:id`

Primary "explain this work" page. Show identity, state, hierarchy, objective, plan, assurance, dependencies, blockers, decisions required, runs, evidence, review, verification, integration/publication, timeline, decisions, provenance/history, and related source/knowledge references.

### `/runs` and `/runs/:id`

Active/recent run browser with role, work, profile/model if exposed, status, timing, latest activity, result, evidence, and provenance. No terminal emulator initially.

### `/evidence` and `/evidence/:id`

E12-compatible evidence browser/detail with result, currentness, claim, findings, deviations, `requires_disposition`, evaluator/environment/bindings, body, provenance, and links.

Sanitize Markdown.

### `/knowledge`

Human-oriented durable knowledge browser grouped by decisions, plans, investigations/research, evidence, reviews/verification, project maps, and other durable records. Not a filesystem browser.

### `/history` and `/history/:id`

ADR-0011 capability. Paginated/bounded.

Show history-integrity state: current root/status, verified status, last full audit, backlog count/age, and contradictions if reported.

Historical detail must display a strong banner:

> Historical reference. This record is not automatically current authoritative evidence.

Show annotations/lineage and superseding/move/promotion links.

### `/queue`

M4 capability. Show `QUEUED`, `LEASED`, `DEFERRED`, `AWAITING_DISPOSITION`, commit-ready sequence, lease/custodian, reason, attempt, publication mode if exposed, current-head binding, and latest integration validation.

No runnability inference and no reorder/defer controls.

### `/graph`

Bounded XYFlow relationship explorer from a selected object. Relations may include hierarchy, dependencies, evidence, decisions, invocations, review, verification, and provenance/history. Default graph should stay below ~100 nodes.

### `/metrics`

Capability-gated measurements only: work state counts, run durations, review/verification turnaround, queue wait, Lead/model usage, refusal/error trends, archive/audit health. Use Recharts if implemented.

### `/activity`

Bounded meaningful events: transitions, decisions, completed runs, reviews, verification, integration, important anomalies, history-audit events. Not every tool call.

## 10. Global search / command palette

`Cmd/Ctrl-K` may open/navigate to work, run, evidence, decision, history record, queue, attention, or filtered views.

No mutation actions.

Use backend search for large/history datasets:

```text
GET /api/v1/search?q=...&kinds=work,evidence,decision,history&limit=50
```

Fuse.js is only for already-loaded bounded sets.

## 11. Provisional dashboard HTTP contract

This contract exists to let the frontend proceed. It is not an AEW authority schema.

Rules:

- version under `/api/v1`;
- GET/HEAD only;
- timestamps are ISO-8601 UTC;
- IDs are opaque strings;
- string enums tolerate unknown future values and must never map unknown to a success/normal style;
- large lists are paginated/bounded;
- no raw `.aew` storage;
- backend conclusions include machine reason codes and optional display text;
- unknown response fields are ignored;
- every successful response carries `control_revision` and `generated_at`;
- resources suitable for polling support conditional GET (`ETag` / `If-None-Match`, returning `304` when unchanged);
- Overview should preferably come from one backend snapshot/composite projection instead of stitching separately polled authority views together;
- health, when present, is a backend conclusion, never a frontend inference.

Recommended response envelope:

```json
{
  "schema": "aew/dashboard/v1",
  "project_id": "spt",
  "control_revision": 843,
  "generated_at": "2026-10-02T04:00:00Z",
  "data": {}
}
```

Error:

```json
{
  "schema": "aew/dashboard/error/v1",
  "code": "NOT_FOUND",
  "message": "work item T-0042 was not found",
  "details": {}
}
```

### Snapshot and health semantics

The adapter should expose one coherent top-level projection, for example:

```text
GET /api/v1/overview
```

that contains the shell status, attention summary and active-run summary from one Engine read revision. Detail pages may poll independently.

If a page still combines responses from multiple revisions, the UI must display the mixed-revision condition until they converge.

Recommended backend health shape:

```ts
type BackendHealth = {
  status: "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "UNKNOWN" | string
  reasons?: Reason[]
  observedAt: string
}
```

Unknown health values render as UNKNOWN.

### Capabilities

`GET /api/v1/capabilities`

Example data:

```json
{
  "history": true,
  "integration_queue": false,
  "action_projection": false,
  "metrics": false,
  "project_maps": false,
  "search": true
}
```

### Proposed endpoints

```text
GET /api/v1/capabilities
GET /api/v1/project
GET /api/v1/overview
GET /api/v1/activity
GET /api/v1/work
GET /api/v1/work/{id}
GET /api/v1/work/{id}/graph
GET /api/v1/runs
GET /api/v1/runs/{id}
GET /api/v1/evidence
GET /api/v1/evidence/{id}
GET /api/v1/decisions
GET /api/v1/decisions/{id}
GET /api/v1/knowledge
GET /api/v1/knowledge/{kind}/{id}
GET /api/v1/history
GET /api/v1/history/{id}
GET /api/v1/history/{id}/links
GET /api/v1/queue
GET /api/v1/attention
GET /api/v1/search
GET /api/v1/metrics
```

## 12. Core provisional DTOs

These are UI DTOs, not durable AEW schemas.

```ts
type EntityRef = {
  id: string
  kind: string
  title?: string | null
}

type Reason = {
  code: string
  message?: string | null
}

type RichText = {
  format: "markdown" | "plain" | string
  text: string
}

type WorkListItem = {
  id: string
  kind: "epic" | "story" | "ticket" | string
  title: string
  state: string
  parentId?: string | null
  mutating?: boolean | null
  revision?: number | null
  classification?: string | null
  assurance?: string | null
  hasAttention: boolean
  updatedAt?: string | null
}

type AttentionItem = {
  id: string
  kind: "decision_required" | "blocker" | "required_finding" | "anomaly" | string
  severity?: string | null
  subject: EntityRef
  title: string
  summary?: string | null
  reasonCodes?: Reason[]
  firstSeenAt?: string | null
}

type EvidenceDetail = {
  id: string
  kind: string
  result?: string | null
  subject?: EntityRef | null
  currentness?: string | null
  requiresDisposition?: boolean | null
  claim?: RichText | null
  body?: RichText | null
  findings?: unknown[]
  deviations?: unknown[]
  bindings?: Record<string, unknown> | null
  evaluator?: Record<string, unknown> | null
  environment?: Record<string, unknown> | null
  provenance?: unknown[]
}

type QueueEntry = {
  id: string
  work: EntityRef
  state: "QUEUED" | "LEASED" | "DEFERRED" | "AWAITING_DISPOSITION" | string
  commitReadySeq?: number | null
  position?: number | null
  reason?: string | null
  attempt?: number | null
  publicationMode?: "PUBLISH_IF_CLEAN" | "VALIDATE_ONLY" | string | null
  lease?: { custodian?: string | null; startedAt?: string | null } | null
  currentBase?: string | null
  latestValidation?: unknown | null
}
```

The API layer should be centralized so backend reconciliation later affects one module, not every page.

## 13. MSW fixture matrix

Create named fixture worlds.

- **F0 Empty/new project:** no active work/runs/history/attention.
- **F1 Normal active:** multiple Epics/Stories/Tickets, runs, evidence, decisions.
- **F2 Attention-heavy:** decision required, blocker, required finding, stale evidence, failed verification, anomaly.
- **F3 ADR-0011 history:** current + archived work, moved/superseded annotations, verified root.
- **F4 History-integrity problem:** verified behind current, backlog, old full audit, contradiction/corruption reported by backend.
- **F5 M4 queue:** queued, leased, deferred, awaiting disposition, validate-only, publish-if-clean, moved-head/rebuild summary.
- **F6 Large active frontier:** 1,000 open/planned units.
- **F7 Large history:** server-paginated history representing tens of thousands of records; never fetch all at once.
- **F8 Long/hostile content:** long Markdown, code blocks, JSON bindings, findings, malformed/untrusted HTML for sanitization tests.
- **F9 Capability downgrade:** history/queue/attention/metrics unavailable.
- **F10 Backend errors:** 404, server error, unavailable network, malformed response rejected by Zod.
- **F11 Honesty/consistency:** unknown enum values, capability absent, backend health UNKNOWN, stale cached payload after failed poll, and intentionally mixed control revisions.

## 14. Rich features allowed because this is not time-critical

These are valid parallel stretch goals as long as they preserve the authority boundary.

### Relationship/provenance graph

High-value. Bounded XYFlow neighborhood around Ticket/plan/decision/evidence/invocation/review/verification/history.

### Compare view

Read-only diff between backend-supplied records/revisions: plan revisions, evidence versions, historical vs current, review/verification summaries. `react-diff-viewer-continued` is available.

### Knowledge search workbench

Grouped results across Work, Evidence, Decisions, History, Runs, Plans/Research with deep links and keyboard navigation.

### Timeline explorer

Per-work/project timeline filtered by transitions, runs, evidence, decisions, review, verification, integration, history/audit.

### Integrity center

ADR-0011-specific current/verified/full-audit status, backlog, audit findings, migration/schema status, contradictions.

### Model/resource observability

If backend later exposes it: provider/model/profile, duration, token/cost, Lead vs worker cost, retries, outcomes.

### Browser-local UI preferences

Allowed: theme, sidebar state, columns, page size, recent searches, graph layout. Never store workflow state locally.

### Deep-linkable filters

Examples:

```text
/work?state=VERIFY_PENDING&attention=1
/evidence?requiresDisposition=1
/history?kind=decision&subject=T-0042
```

## 15. Polling and backend-load contract

The dashboard must not recreate the control-plane reparse pathology ADR-0011 is removing.

### 15.1 Conditional GET is required for polled resources

Polled responses return an `ETag` keyed at least by the AEW control revision and representation.

Example:

```http
ETag: W/"aew-dashboard-v1-overview-r843"
```

The browser sends:

```http
If-None-Match: W/"aew-dashboard-v1-overview-r843"
```

If unchanged, the adapter returns `304 Not Modified` without rebuilding the projection.

### 15.2 Normal dashboard reads must not become control commits/lock-heavy reads

The read adapter must serve ordinary polling from a non-authoritative, revision-keyed projection cache.

Requirements:

- a 2-second browser poll must not take the AEW commit lock merely to discover nothing changed;
- a poll must not re-parse full authoritative state when the current revision is unchanged;
- projection/cache contents are derived and disposable;
- cache loss affects performance, never authority;
- cache refresh happens once per observed revision, not once per browser request;
- the final backend design may use commit notification, a lightweight file/revision watcher, or another mechanism that satisfies these properties.

This is an integration/backend requirement, not something the browser is allowed to solve by reading AEW files itself.

### 15.3 Measure it

Integrated acceptance should record:

- request rate under the default polling cadence;
- 304 rate during an idle project;
- Engine/control-state parse count;
- lock acquisitions attributable to dashboard GETs;
- CPU cost with one dashboard open.

An idle dashboard must remain cheap.

## 16. Security constraints

Even read-only AEW data may expose sensitive engineering state. Security controls are mandatory.

### 16.1 Authenticated local session

Loopback binding is necessary but not sufficient: other local processes, including agent shell processes, can reach loopback.

The dashboard API therefore requires a high-entropy, per-session bearer capability.

Recommended flow:

1. AEW generates at least 128 bits of cryptographically random session secret.
2. AEW opens/prints a one-time bootstrap URL on `127.0.0.1:<port>`.
3. The bootstrap exchange establishes an authenticated browser session (prefer an `HttpOnly`, `SameSite=Strict` session cookie) and redirects to a clean URL.
4. The bootstrap token is single-use and not retained in browser history after redirect.
5. API requests without the authenticated session are rejected.
6. The session is invalidated when the owning AEW dashboard/server exits.

Never put provider keys, AEW authority credentials, harness server passwords, or other secrets into frontend JavaScript.

### 16.2 Host and Origin validation

The server binds to `127.0.0.1` by default and validates requests:

- `Host` must match the actual loopback host/port accepted by the server;
- API requests carrying `Origin` must match the exact dashboard origin;
- unexpected hosts/origins are rejected;
- do not use permissive CORS.

This is defense against DNS-rebinding/cross-origin access, not a replacement for the session token.

### 16.3 Strict browser policy

Serve, at minimum, a CSP equivalent to:

```text
default-src 'self';
script-src 'self';
style-src 'self';
img-src 'self' data:;
connect-src 'self';
font-src 'self';
object-src 'none';
base-uri 'none';
frame-ancestors 'none';
form-action 'none';
```

Prefer no inline scripts/styles so CSP does not require `'unsafe-inline'`.

Also send:

```text
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Cross-Origin-Resource-Policy: same-origin
```

### 16.4 Untrusted record rendering

Agent/model/external-authored record text is untrusted display data.

- sanitize Markdown;
- do not execute raw HTML;
- disable remote Markdown images in V1 (render a placeholder/link instead);
- external links get `rel="noopener noreferrer"` and must not auto-fetch;
- no CDN, analytics, remote fonts, external scripts, or automatic remote embeds.

### 16.5 Security test obligations

Integrated tests must prove:

- unauthenticated API request is rejected;
- wrong Host is rejected;
- wrong Origin is rejected;
- CSP and security headers are present;
- hostile Markdown cannot execute script or trigger remote image fetch;
- secrets are absent from DTOs;
- dashboard session expires with its owning process.

## 17. Performance constraints

Do not turn history back into a hot path.

- no fetch-all-history startup;
- paginate/bound large collections;
- virtualize large active lists;
- lazy-load detail tabs;
- bound graph depth/node count;
- cache with React Query;
- ordinary polling first;
- route changes must not cause project-wide scans.

Suggested UI targets:

- shell interactive in under ~1s after local assets load;
- 1,000-row active list scrolls smoothly with virtualization;
- default graph under ~100 nodes;
- no route requires loading full cold history.

## 21. Refresh model

Start with polling, not WebSockets.

Suggested defaults:

- the composite Overview projection: ~2s;
- work/queue lists: 3–5s;
- detail records: focus refresh or 5–10s;
- historical lists: manual or low-frequency refresh.

Every poll uses `If-None-Match` when an ETag is available.

On refresh failure:

- keep the last good payload visible;
- mark it `STALE` or `DISCONNECTED`;
- show last successful `generated_at`, control revision and age;
- never silently present React Query cache as current.

SSE may be added later without changing page semantics.

## 20. Contract ownership and early review gate

The provisional DTOs exist to enable parallel work, but they must not become accidental architecture.

### C0 — DTO review gate

Before the frontend treats the DTO layer as frozen:

1. the frontend worker produces one versioned contract file (`web/src/api/schemas.ts` plus an exported JSON/OpenAPI-like description, or an actual OpenAPI draft);
2. the **main-line AEW owner/reviewer** reviews the domain shapes;
3. review checks names, identity semantics, pagination, reason codes, capability behavior, queue fields, history/currentness representation, and revision metadata;
4. accepted DTOs are tagged/versioned for MSW fixtures;
5. later backend OpenAPI becomes authoritative and generated TypeScript replaces hand-maintained duplicates.

Until C0 passes, the frontend may build the shell, generic components, loading/error states, and clearly provisional fixtures, but should avoid spreading semantic DTO assumptions through page components.

A contract change after C0 is allowed; it must update schemas, fixtures and conformance tests together.

## 21. Core-vs-optional scope gate

The initial integration target is deliberately bounded.

**Core (D0–D4):**

- shell;
- Overview;
- Work;
- Runs;
- Evidence/Knowledge;
- History/integrity;
- Attention;
- Queue;
- degraded/stale/mixed-revision behavior.

**Optional after core freeze:**

- graph;
- compare/diff;
- global search / Cmd-K;
- timeline explorer;
- metrics/observability.

The optional track may continue because it is non-blocking, but it cannot delay integration/review of the core and it cannot pre-load its dependency surface before use.

## 22. Testing strategy

### Unit/component

Vitest + Testing Library. Test badges/states, capability gates, filters, pagination, detail sections, Markdown sanitization, graph nodes, error states, deep links.

### Contract

Validate all fixture/real responses with Zod. When backend OpenAPI exists, use `openapi-typescript` and generated types rather than maintaining a second permanent schema by hand.

### MSW

Every major route must run against the fixture worlds.

### Playwright

Core smoke path:

1. Overview;
2. Work → work detail;
3. Evidence detail;
4. History detail;
5. capability downgrade;
6. stale/disconnected cache state;
7. mixed-revision state;
8. unknown enum rendering;
9. verify absence of mutation controls.

Optional-feature smoke tests (graph/search/metrics) join only if those features land.

### Mandatory adversarial UI tests

Explicitly test:

- unknown enum/state is visibly UNKNOWN, never green/normal;
- capability absent renders unavailable, never zero/healthy;
- backend health is displayed only when provided;
- stale cache after polling failure is visibly stale;
- mixed control revisions are visibly mixed;
- hostile Markdown cannot execute HTML/script and remote images do not load;
- unsupported capability routes degrade cleanly.

### Offline build

Mandatory using the existing Node 22 toolchain with networking disabled.

## 23. Frontend acceptance and independent-review gates

Frontend-only work is ready for integration when:

1. production build succeeds offline using the existing SPT toolchain;
2. typecheck/lint/tests pass;
3. Playwright smoke passes;
4. all routes work against MSW;
5. capability downgrade works;
6. large-list fixture remains responsive;
7. Markdown is sanitized;
8. no mutation API methods exist in the client;
9. no frontend code knows `control.yaml`, cold-bundle paths, manifests, SQLite, or Engine internals;
10. backend conclusions are displayed, not recomputed;
11. light/dark both work;
12. deep links are stable;
13. static `dist/` is produced;
14. C0 DTO review has passed for the core contract;
15. explicit unknown/capability/stale/mixed-revision tests pass.

### R-FE — Independent frontend review

Passing MSW and component tests is verification, not independent review. Before the core frontend PR is considered integration-ready, a reviewer who did not implement it performs an adversarial review focused on:

- accidental authority inference;
- unknown enum handling;
- capability-absent honesty;
- stale/mixed-revision behavior;
- XSS/Markdown/external-resource behavior;
- dependency creep;
- no mutation controls/client methods;
- no `.aew`/Engine-storage coupling;
- DTO assumptions that escaped the centralized API layer.

Findings are dispositioned before frontend freeze.

### R-INT — Integrated security/load review

After the real adapter/server is connected, an independent review additionally verifies:

- session authentication;
- Host/Origin validation;
- CSP/security headers;
- no secret leakage;
- ETag/304 behavior;
- dashboard polling does not produce per-request control-state parses/lock acquisitions;
- one open idle dashboard remains cheap.

## 24. Integration-phase responsibilities

Intentionally left for the main/integration line:

- authoritative Engine read projections;
- read-only HTTP adapter;
- final contract reconciliation;
- Python package/static-asset packaging;
- server lifecycle;
- mandatory authenticated loopback session, Host/Origin validation, CSP/security headers;
- revision-keyed projection cache plus ETag/304 behavior;
- coherent Overview snapshot projection;
- `aew opencode` / possible `aew dashboard` wiring;
- end-to-end test against real AEW state;
- final OpenAPI generation.

The frontend worker should make integration cheap by centralizing all API access.

## 25. Suggested source layout

```text
web/
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── app/
│   ├── api/
│   │   ├── client.ts
│   │   ├── schemas.ts
│   │   ├── types.ts
│   │   └── mock/
│   ├── components/
│   │   ├── shell/
│   │   ├── badges/
│   │   ├── tables/
│   │   ├── markdown/
│   │   ├── graph/
│   │   ├── timeline/
│   │   └── attention/
│   ├── pages/
│   ├── lib/
│   └── styles/
└── tests/
    ├── component/
    ├── integration/
    └── e2e/
```

## 26. Implementation sequence for the second LLM

Because there is no immediate deadline, prefer architectural cleanliness over a tiny throwaway MVP.

### D0 — Contract + skeleton

- create `web/`;
- choose the lean D0–D4 dependency subset only;
- define provisional DTOs/Zod schemas;
- implement capabilities mock;
- create F0–F11 fixture worlds;
- set up React Query/Router/Tailwind/Radix;
- prove offline build;
- submit the DTO/contract file for **C0 main-line review** before semantic DTO assumptions spread through the app.

### D1 — Shell + Overview + Work

- navigation shell;
- status header;
- Overview;
- Work tree/table/detail;
- deep links;
- virtualization.

### D2 — Runs + Evidence + Knowledge

- runs browser/detail;
- evidence browser/detail;
- sanitized Markdown;
- knowledge/decision views.

### D3 — History + integrity UX

- history list/detail;
- lineage/annotations;
- history audit/integrity panel;
- historical-reference warning;
- large-history pagination fixtures.

### D4 — Attention + Queue

- decisions required;
- blockers;
- required findings;
- anomalies;
- integration queue.

Both capability-gated.

### D5 — Optional: Graph + Timeline + Search

- bounded XYFlow graph;
- project/work timeline;
- global search / Cmd-K;
- deep-linked filters.

### D6 — Optional: Metrics + compare/polish

If telemetry exists in fixtures:

- charts;
- usage/duration views;
- responsive polish;
- accessibility;
- keyboard navigation;
- loading skeletons;
- empty/error states;
- optional compare views.

### D7 — Frontend freeze for integration

- all mock worlds green;
- offline build proof;
- Playwright green;
- document provisional API assumptions;
- do not start changing Engine/backend just to integrate.

At D7 the frontend can wait safely for the real adapter.

## 27. Definition of success

The dashboard succeeds if the operator can leave it open next to the Lead and understand AEW without repeatedly asking the Lead for status.

```text
Lead:
    handles engineering and asks for judgment only when needed.

Dashboard:
    shows what is happening,
    what AEW knows,
    why it believes it,
    what changed,
    what is historical,
    what needs attention,
    and how the evidence connects.
```

The design must preserve AEW's core architectural principle:

> **Authority and workflow semantics live in one place. Interfaces reveal them; they do not reinvent them.**
