# Frontend architecture and authority

The read-only React/Vite frontend validates accepted payloads in `src/api/schema.ts`; `src/api/types.ts` is generated from accepted API 0.1.2. Transport/read contexts own request policy, conditional validators, retirement and scope isolation. Safe content, shared workspace, source display, tabs and focus helpers provide consistent presentation.

`src/api/preview/{journal,investigation,evidence,execution}/` owns separate provisional models, strict schemas, registrations, fixtures, projectors, read contexts and UI. Demo-only dynamic imports keep these interfaces and initialization out of production. Canonical artifacts and fixture manifests stay in `docs/design/`; artifact checks detect drift. Preview validators cannot weaken accepted parsing or route restrictions.

Worker handlers and `scripts/demo-server.mjs` use shared projectors. HTTP demo mode supports locked-down browsers without registering a service worker; Stateful Scenario Lab recipes retain the worker path. Neither adapter implements Engine persistence, authorization or live integration.

Read identities include contract/dataset/case/project/session and exact source/snapshot/object ownership as applicable. Reference associations differ from canonical Evidence IDs; artifact identity includes ID and revision. Views retire obsolete requests, clear refused data and retain visibly stale valid data on ordinary refresh failure. Fixed snapshots never advance silently.

The browser renders supplied claims, typed relations and explicit groupings. It never infers topics, membership, supersession, contradiction, causality, budget enforcement or workflow legality. Packet preparation, delivery, citation and evaluated benefit remain reusable distinct concepts. Canonical decisions point to their authoritative records. Evidence ownership remains independent of Knowledge Capture & Admission.

Execution previews have explicit T3/outbox and G7/F7 firewalls and project-only visibility; live adoption requires Engine-owned adapters. See the [approved plans](../design/plans/README.md) and [backend question ledgers](../reference/backend-questions/README.md).
