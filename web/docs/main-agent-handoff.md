# Main AEW agent handoff: accepted C0 / core review candidate

Candidate branch `feat/aew-dashboard-readonly`, worktree `../AEW-dashboard`.
Accepted review target: `322301d1200dce54d31a54348dd15ba7a71c9376`.
Version **0.1.2**, SHA-256 **`68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`**.
Diff base: previously reviewed candidate `7b0177b76a919e019d2051adff8f7616ae6c2fda`.

`c0-review-main-line-0.1.1.md` is retained unchanged. Its conditional acceptance requires exactly R2-1–R2-6 and main-line verification of this diff. `c0-review-packet.md` maps the six changes to their companion artifacts/checks. The two boundedness proposals and curated projections are now accepted as stated in that review. No further contract amendment is included.

Changes: unique GET/HEAD parameters; opaque fingerprint/digest strings; path-free relation documentation and commit-hash fixture links; subtree Ticket rollup clarification; P2c verified/full/oldest-unverified metadata; known `lost` harness status. Version/hash pins, generated types, Zod, F0–F11 and tests are synchronized. P2c source was inspected at `bdabff9` and fingerprint source at `91c0d98` using read-only Git reads; no engine tests or code changes were made.

Claude verified the mechanical diff and recorded ACCEPT in `c0-review-main-line-0.1.2.md` and `c0-approval.json`, dated 2026-10-02. D1–D4 may begin. The exact YAML is unchanged; frontend acceptance pins and tests now match the signed record. Independent frontend review and live integration remain separate.

Validation scope and evidence are in `validation-c0-012.md`. The same immutable SPT builder and dependency/lock/browser identities are used; retest notes are appended to `spt-toolchain-feedback.md`. Production contains the core read-only pages, validated through a test-only same-origin fixture adapter. Queue is UNSUPPORTED with no wire model; integrity remains provisional and UNSUPPORTED for the frozen pre-P2c baseline, becoming AVAILABLE when the merged backend advertises it.

The original AEW checkout and concurrent tests remain untouched. Engine semantics, shared reason-code registry, authentication/bootstrap, serving/security headers, Host/Origin validation, projection caching, Python packaging and live-state integration remain main-line ownership. Frontend core review and integrated-system acceptance remain separate from C0.

## D1 handoff

Overview, filtered bounded Work table/tree, virtualization, cursor pagination and opaque-ID details are implemented without new dependencies. Backend owns all domain conclusions. `validation-d1.md` records the immutable offline gate (51 tests) and 18 compiled browser checks; `d1-visual-review.md` supplies running previews and screenshots. The user approved this visual direction on 2026-10-02, and D2–D4 are now implemented. Independent frontend review at core freeze remains a separate main-agent gate. Test-adapter success does not establish live-state/authentication integration.

## Optional Work graph request

The user identified large-project epic/story/ticket hierarchy and linkage as a useful graph use case. `work-graph-follow-up.md` records a proposed Work Graph view alongside Table/Tree, with focused bounded exploration and an explicit backend contract prerequisite. It remains separate work after core freeze; no graph implementation or date is claimed.

## Core review handoff

The main reviewer returned AMEND (minor) for frozen `e632cc8`; the actual static-review return is retained unchanged in `frontend-core-review-main-line.md`. FR-1/FR-2 are fixed at **`7c120b4c39a059508e3b095a9bfd5498c1d7be09`**. See `frontend-core-review-fix-response.md` for 73 passing offline tests, 34 compiled browser checks, five failing pre-fix negative controls and exact review commands. Contract and lock remain unchanged. Main-line fixing-diff verification/ACCEPT is pending; core freeze and integrated-system acceptance are not asserted. Current export: `artifacts/aew-dashboard-core-7c120b4.tar.gz`; prior frozen evidence is retained.

`frontend-core-review-packet.md` supplies the frozen implementation target, exact scope, retained evidence and review protocol. `validation-core.md` records 61 tests and 18+12 compiled browser checks. `integration-checklist.md` distinguishes frontend review from live-system acceptance. Queue remains unavailable without an accepted wire model; integrity rendering is capability-gated, with AVAILABLE exercised only by a clearly synthetic test projection. The accepted contract, lock and fixture bytes did not change. No Engine tests or source edits occurred. Required next gate: actual main AEW agent independent frontend review and finding disposition before core freeze.
