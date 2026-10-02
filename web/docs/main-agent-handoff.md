# Main AEW agent handoff: 0.1.2 mechanical C0 diff

Candidate branch `feat/aew-dashboard-readonly`, worktree `../AEW-dashboard`.
Review target: the commit containing this handoff and canonical OpenAPI contract.
Version **0.1.2**, SHA-256 **`68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`**.
Diff base: previously reviewed candidate `7b0177b76a919e019d2051adff8f7616ae6c2fda`.

`c0-review-main-line-0.1.1.md` is retained unchanged. Its conditional acceptance requires exactly R2-1–R2-6 and main-line verification of this diff. `c0-review-packet.md` maps the six changes to their companion artifacts/checks. The two boundedness proposals and curated projections are now accepted as stated in that review. No additional design proposal or domain expansion is included.

Changes: unique GET/HEAD parameters; opaque fingerprint/digest strings; path-free relation documentation and commit-hash fixture links; subtree Ticket rollup clarification; P2c verified/full/oldest-unverified metadata; known `lost` harness status. Version/hash pins, generated types, Zod, F0–F11 and tests are synchronized. P2c source was inspected at `bdabff9` and fingerprint source at `91c0d98` using read-only Git reads; no engine tests or code changes were made.

Please verify only the candidate diff against `7b0177b`, then return the full candidate commit, version/digest, reviewer/date and accepted disposition. `c0-approval.json` retains both AMEND reviews and keeps 0.1.2 PENDING until that verification is recorded. D1–D4 remain gated.

Validation scope and evidence are in `validation-c0-012.md`. The same immutable SPT builder and dependency/lock/browser identities are used; retest notes are appended to `spt-toolchain-feedback.md`. Production remains the generic pending-integration shell. Queue is UNSUPPORTED with no wire model; integrity remains provisional and UNSUPPORTED for the frozen pre-P2c baseline, becoming AVAILABLE when the merged backend advertises it.

The original AEW checkout and concurrent tests remain untouched. Engine semantics, shared reason-code registry, authentication/bootstrap, serving/security headers, Host/Origin validation, projection caching, Python packaging and live-state integration remain main-line ownership. Frontend core review and integrated-system acceptance remain separate from C0.
