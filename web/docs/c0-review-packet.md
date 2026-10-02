# C0 final mechanical resubmission: dashboard API 0.1.2

Status: **ACCEPTED** by Claude, 2026-10-02, at commit `322301d1200dce54d31a54348dd15ba7a71c9376`. See `c0-review-main-line-0.1.2.md` and the signed record in `c0-approval.json`. D1–D4 may begin.

Canonical artifact: `docs/design/dashboard-api-v1-provisional.yaml`.
SHA-256: `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`.
The frozen accepted target is `322301d1200dce54d31a54348dd15ba7a71c9376`. The YAML remains byte-identical to that target, including its historical provisional/review labels; the external acceptance record governs implementation eligibility.

Claude's retained review, `c0-review-main-line-0.1.1.md`, conditionally accepts a 0.1.2 that applies exactly R2-1–R2-6. It confirms C0-1–C0-9 are resolved in substance and accepts child-list truncation, subtree rollup, annotation paging, null normalization and curated path-free bindings. No new design decision or domain page is introduced in this resubmission.

## Mechanical correction map

| Finding | Correction and companion checks |
|---|---|
| R2-1 | Deduplicate parameters by name/location on `/work`, `/evidence`, `/history` and `/history/{id}`, for GET **and HEAD**. Test every operation, with a duplicate-parameter negative control. |
| R2-2 | Fingerprint and artifact digest items are opaque strings. Fixtures use `git-tree:<hex>` and opaque digest strings; both canonical and runtime validators accept those and reject non-string values. |
| R2-3 | Document backend omission of `completion`, and link values as AEW IDs or git commit hashes. Declare today's seven known relations. Fixtures include `integration_commit`; both validators reject completion storage paths. The frontend does not sanitize or infer a storage mapping; projection omission belongs to main-line integration. |
| R2-4 | Clarify that parent rollup counts Tickets across the entire subtree, including archived terminals; direct IDs remain in `children`. Overview's count meaning is preserved. Epic fixture counts now demonstrate one direct Story but three open and one DONE subtree Tickets. |
| R2-5 | Extend verified roots with timestamp/audit identity; add nullable `last_full` and `oldest_unverified_at`. Describe backend over-policy reasons. Match engine P2c `bdabff9`; keep `x-provisional: P2c` and baseline UNSUPPORTED capability until merge, with AVAILABLE advertised by integration afterward. F4 demonstrates distinct verified/full records and metadata validation. No frontend thresholds or backlog arithmetic added. |
| R2-6 | Add `lost` to known harness statuses; a presentation test verifies it does not render as unknown. Semantic strings stay open. |

Only those corrections, the 0.1.2 version/digest pins, generated types, fixtures, conformance tests and review/evidence bookkeeping changed. No package, lock, builder, route, UI layout or workflow semantic change accompanies them. Earlier review documents remain intact.

## Verification and recording

Companions: generated `web/src/api/types.ts`, strict `schema.ts`, `vocabulary.ts`, `contract-version.json`, fixtures F0–F11 and the focused contract/content tests. Current evidence: `web/docs/validation-c0-012.md`.

`c0-approval.json` retains both previous AMEND reviews, including the conditional 0.1.1 review of `7b0177b76a919e019d2051adff8f7616ae6c2fda`. Main line verified the diff and recorded ACCEPT with the exact commit/digest, reviewer and date. The frontend acceptance pins and tests now identify that record. The main-line review did not rerun frontend checks; those remain separately recorded frontend evidence.

The recorded gate permits D1–D4 to begin under the approved core plan. Independent frontend review at core freeze and integrated-system acceptance remain separate gates.
