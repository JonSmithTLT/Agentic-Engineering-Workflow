---
title: "SPT / Agent Toolchain Remediation Backlog"
subtitle: "Implementation Appendix — v0.2"
date: "September 25, 2026"
---

# 1. Purpose

Capture concrete tooling/image defects found during the SPT audit separately from AEW architecture. Audit result indicates roughly 80–90% of the existing SPT environment is usable; remaining work is concentrated.

This document is a **bootstrap remediation authority only until the minimum AEW Work Graph is operational**. At that point, unresolved remediation work is imported into AEW as an Epic/Stories/Tickets and the AEW Work Graph becomes the live scheduling/to-do authority. This document then remains source/reference material and must not continue as a parallel mutable backlog.

# 2. GitNexus

## 2.1 Ownership / permissions

Artifacts are currently owned by the `spt` image/runtime user rather than the actual work user.

Required outcome:

- runtime directories/mounts writable by the effective host developer UID/GID;
- avoid hard-coded usernames;
- do not recursively `chown` arbitrary project source;
- rootless/container mapping preferred where practical.

Acceptance: create/index, stop container, edit/delete artifacts as work user, restart, reuse index.

## 2.2 Persistence

Move derived indexes/artifacts away from temporary-only storage to explicit persistent mounts/volumes.

Persist indexes/project graph metadata and optional model assets; keep scratch/IPC transient.

Tag derived state with project/worktree identity, source revision, GitNexus version, and configuration so stale/incompatible state is detectable.

## 2.3 Lightweight repository explorer

The existing Python-based Git/repository exploration path is **not** a separate "GitNexus Lite" product. Formalize it as a complementary/fallback `repository_exploration` provider.

Use it for fast history/diff/tree/basic traversal. Use GitNexus for richer relationship/impact discovery. Do not claim GitNexus semantics from the lightweight explorer.

# 3. Reusable container UID/GID startup pattern

Create managed service directories using the configured/effective host UID/GID. Dynamic user creation/remapping may be used where necessary. Apply ownership only to known managed paths.

This pattern should be reusable across containerized services.

# 4. Ghidra bridge

## 4.1 Remote/server artifacts

Current bridge works with local binaries only. Add a controlled remote/server artifact staging path.

Required flow:

```text
remote/test target
  -> controlled retrieval/staging
  -> hash + source provenance
  -> local analysis artifact identity
  -> Ghidra/Ghidra MCP
```

Record original host/path/source reference where appropriate, binary hash, local staging identity, and cleanup/persistence policy.

## 4.2 Environment configuration

Capture the additional environment variables required by the current Ghidra bridge from the working/audited environment. Do not invent variable names in implementation.

Acceptance: select remote binary, stage, hash, analyze, query via MCP, restart, verify persistence/provenance.


# 5. AEW capability mapping

The remediation work should satisfy named Workbench Capability Contract needs rather than remain orphaned infrastructure.

| Remediation/provider | AEW capability mapping | Notes |
|---|---|---|
| Lightweight Python repository explorer | `repository_exploration` | Fast Git/history/tree/basic traversal fallback/complement |
| GitNexus | `relationship_discovery`, call/impact capabilities where supported | Derived relationship provider; not authority |
| Remote/test-host retrieval path | `remote_artifact_acquisition` | Approved remote artifact retrieval with source provenance |
| Local binary normalization/staging | `binary_artifact_staging` | Hash + attributable local staging identity |
| Ghidra / Ghidra MCP | `binary_analysis` | Analyze staged/local binary |
| Ghidra call graph/export features | `call_graph_query`, `call_graph_export`, `interprocedural_impact_analysis` where provider support exists | Derived evidence |
| Future function-level abstraction | `function_analysis` (TBD) | Exact semantics remain open; not a blocker for P0 bridge work |

The Ghidra P0 work therefore does **not** wait for `function_analysis` to be defined. Its minimum contract is remote acquisition/staging plus binary analysis with provenance.

# 6. Image/runtime compatibility

Most tools currently run even where images were built on a newer distro than the Rocky 8 development target. Treat this as packaging/reproducibility debt rather than an immediate functional blocker.

Pin per image/provider:

- base/build distro;
- architecture;
- upstream version/commit;
- dependency/runtime versions;
- image digest;
- offline export/import procedure.

# 7. Doctor checks

Target doctor surface:

```text
host tools                  PASS
container runtime           PASS
GitNexus service            PASS
GitNexus writable mount     PASS
GitNexus persistence        PASS
repo explorer               PASS
Ghidra MCP                  PASS
Ghidra remote staging       PASS
browser service             PASS
memory service              PASS / OPTIONAL
provider gateway            PASS
```

Failures should report concrete ownership, mount, environment, compatibility, or connectivity problems.

# 8. Priority

## P0

1. GitNexus persistent storage.
2. GitNexus UID/GID/ownership correctness.
3. Ghidra bridge remote/server artifact support.
4. Capture/package Ghidra bridge environment configuration.

## P1

5. Reusable container ownership/startup pattern.
6. Doctor checks for mounts/writeability/persistence.
7. Validate Rocky 8 import/runtime compatibility for current images.
8. Formalize lightweight repository explorer provider/fallback semantics.

## P2

9. Image/base-distro optimization after functionality is stable.


# 9. Bootstrap-to-self-host transition

Before AEW minimum implementation exists, this appendix is the remediation backlog authority.

Once AEW can create durable Epics/Stories/Tickets, checkpoint/resume, and show the canonical Work Graph:

1. create an Epic such as `Toolchain Readiness`;
2. import remaining remediation items as Stories/Tickets with dependencies and acceptance criteria;
3. preserve this appendix as source/provenance for the imported work;
4. mark imported items here as migrated/frozen rather than maintaining two live status systems;
5. from that point forward, AEW Work Graph state is the scheduling/to-do authority.

Suggested Story grouping:

- GitNexus durability/permissions;
- Ghidra remote artifact + binary-analysis bridge;
- container UID/GID/runtime packaging hygiene;
- doctor/offline compatibility validation.
