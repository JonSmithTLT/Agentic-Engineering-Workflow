# Main AEW agent handoff: amended C0 candidate

Review the commit containing this handoff on branch `feat/aew-dashboard-readonly`, worktree `../AEW-dashboard`. Canonical artifact: `docs/design/dashboard-api-v1-provisional.yaml`, OpenAPI 3.1, version **0.1.1**, SHA-256 **`3da20f18768d34bef9ccf15fcb65c24cefd2ca73cfc77e6cada8a586f88a0dc4`**.

The original version 0.1.0 at `59081d0136bba947d645c2ec60132e5ca7e12e1a` received **AMEND** from Claude, checked against engine main `91c0d98`. That review is retained intact in `web/docs/c0-review-main-line.md`. Current candidate approval is **PENDING**; D1–D4 have not begun.

`web/docs/c0-review-packet.md` maps all nine findings to contract/client/fixture/test changes. Please confirm two explicit boundedness proposals: parent `children_truncated` with full backend rollup, and history detail `annotations_limit`/`annotations_cursor`/`annotations_next_cursor` pinned to the starting manifest count. Also confirm the documented null normalization and curated path-free evidence bindings. Return the exact candidate commit, version/digest, engine baseline, reviewer/date and disposition.

The original worktree base is `c380aea781736541c3a5f30a5ed4f8bc36227a7f`; amendments were checked against `91c0d98` using read-only engine source inspection. Changes remain limited to `web/` and the canonical YAML under `docs/design/`. No rebase or change to the original checkout, engine semantics, storage schemas or concurrent AEW tests was performed.

The candidate includes generated types, strict Zod, open known vocabularies, all F0–F11 and artifact pins. The demo server exercises explicit archive filtering, bounded pages, hot cursor expiry, history cursors surviving appends and representation-based ETags. These tests prove the provisional client/mock contract, not a live Engine projection adapter. Queue is UNSUPPORTED with no endpoint/model; integrity is UNSUPPORTED pending P2c, with hypothetical examples separated from available responses.

`web/docs/validation-c0-amend.md` records current offline and compiled browser evidence. Production remains a generic integration-pending shell; mock Overview/Ticket previews are clearly provisional. Updated screenshots are under `web/docs/screenshots/`. The previews remain eligible for visual review while C0 is pending.

SPT prerequisite stays separate: commit `ae65ad0408536140a96335e8e76a6245a33ace4a`, branch `build/aew-dashboard-tailwind-cache`, worktree `../SPT-dashboard-toolchain`. Validated immutable Linux/amd64 Node 22 carrier `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`; dependency/lock/cache identities are unchanged for this amendment. See `builder-provenance.json` and the retained ticket-ready `spt-toolchain-feedback.md`.

After C0 acceptance, domain implementation and independent frontend review at core freeze remain required. Authentication/bootstrap, server security headers, Host/Origin validation, projection caching, Python packaging, shared reason-code registry and live-state integration remain main-line ownership. Frontend and integrated-system acceptance must be reported separately.
