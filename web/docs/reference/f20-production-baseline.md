# F20.5 approved frontend build baseline

On 2026-10-05 the operator approved recording the web agent's recommended PR #52 merge commit as the F20.5 production-build baseline: “yup that can be done since it seems to ahve caused confusion here”. This records packaging approval separately from the earlier Work frontend review.

| Identity | Approved value |
|---|---|
| Frontend source commit | `4f0a710fa4831eefda248dd43cc2e144d1010189` |
| Repository tree | `5b75034f65c3aed78ae1eb086024defe284adaa5` |
| Frontend subtree | `348aa372634c88b261e972c363a3ffaf9078b55c` |
| Accepted API | 0.1.2 |
| Contract SHA-256 at that commit | `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691` |
| `web/package-lock.json` SHA-256 | `3cab231b1ea36beabd4352426ca56d9a9c5bdbec14d78ac719b26cb7b369b0b2` |
| `web/package.json` SHA-256 | `a131d0a64c01a4f36529668c6f97d00bff0087250a05ee20efbd16f649eb2382` |
| Pinned builder image | `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407` |
| Toolchain | Node 22.22.2 / npm 10.9.7 |

The main-line agent may rebuild this exact commit under WSL with the [pinned offline builder](../how-to/pinned-web-builder.md). Build from a clean detached checkout using the committed gate; preserve the source/tree identities, commands, production `dist/` and complete file hashes. Record builder/toolchain, contract, package and lock digests in the packaged `BUILD.json`; verify source and build trees remain unchanged after verification. This document does not assert that a new package build has already been produced.

Package the production build only. Provisional Journal, Investigation, Evidence inspection and Execution modules remain excluded. The historical `7c120b4` core freeze remains historical; neither newest main nor a later contract-header amendment silently replaces this approved baseline. A replacement requires another explicit baseline agreement.

F20.6 must name this build's actual `BUILD.json` and served file hashes in its separate integration acceptance. Packaging approval does not establish live browser acceptance or adopt preview contracts. See the [live browser handoff](f20-live-browser-handoff.md), [integration checklist](integration-checklist.md) and [Engine design note](../../../docs/design/proposals/dashboard-main-line-api-design-v0.1.md).
