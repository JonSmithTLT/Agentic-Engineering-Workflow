# Main AEW agent handoff: C0 review first

The frontend worktree is `../AEW-dashboard`, branch `feat/aew-dashboard-readonly`, originally based on AEW main `c380aea781736541c3a5f30a5ed4f8bc36227a7f`. It changes only `web/` and `docs/design/dashboard-api-v1-provisional.yaml`. The original checkout and concurrent engine work remain separate.

Please review the artifact-bearing D0 commit supplied with this handoff. The canonical contract is OpenAPI 3.1, version `0.1.0`, SHA-256 `f956f0b2f1f2de0840667c28301be08b6cc0b462271651a0d3cc9117b6034b70`. `web/docs/c0-review-packet.md` lists eight decisions requiring main-line acceptance or amendment. Return the reviewed commit, exact version/hash, reviewer, findings and disposition. Approval is currently PENDING.

Generated types, Zod validators and F0–F11 are included and conformance-tested. Semantic assumptions stay in the provisional mock module; production is a generic pending-integration shell. D1–D4 domain implementation has not begun. The running mock Overview and Ticket details, plus `web/docs/screenshots/`, are ready for visual review.

SPT prerequisite is separate: fix commit `ae65ad0408536140a96335e8e76a6245a33ace4a`, branch `build/aew-dashboard-tailwind-cache`, worktree `../SPT-dashboard-toolchain`. Validated Linux/amd64 Node 22 carrier `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`. Its full offline smoke, actual Tailwind compilation and checksums passed. No temporary AEW cache workaround exists.

D0 offline installation from empty modules, generator consistency, typecheck, lint, 26 tests and both builds passed in that image with networking disabled. Compiled browser checks using matched Playwright/Chromium also passed. Evidence and limitations are in `web/docs/validation-d0.md`; package/cache provenance is in `builder-provenance.json`; SPT observations and ticket-ready improvements are retained in `spt-toolchain-feedback.md`.

This is a C0 review handoff, not a request to integrate or certify the completed core frontend. Independent frontend review remains required at core freeze; backend/auth/server security/packaging/live-state integration remain main-line ownership. No ongoing AEW test suite was invoked by the frontend work.
