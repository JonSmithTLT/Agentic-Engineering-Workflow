# Paged Activity — existing-contract frontend slice

Operator authorized this slice after the dashboard integration audit. Implement from merged main independently of Settings. Accepted API 0.1.3, generated types, provisional contracts, lock and packaged frontend baseline remain unchanged.

## Experience and reads

Expose `/activity` in navigation and link Overview's Recent activity to it. Read accepted `/api/v1/activity`, capability gated after project bootstrap. Use 50-entry opaque cursor pages, replacing rows rather than accumulating. Preserve the supplied order. Show activity ID, supplied title, full UTC occurrence timestamp, subject and nullable supplied reason. Missing reasons do not establish that no explanation exists.

Existing allowlisted reference destinations remain clickable. Unsupported targets retain identity and raw semantic warnings plus explicit “No detail view available.” Do not reinterpret a transition, Lead or harness-run ID as an invocation or Work record. No new detail API is proposed.

The reader uses the established transport/cache/refusal/stale/obsolete/304 machinery. Activity has no interval or foreground refresh; explicit Refresh page checks the current page. First page returns to the latest window; a cursor pins an older window. Refreshing older pages does not silently replace their cursor with a latest window. Link reload preserves the opaque cursor through the existing presentation allowlist. Invalid duplicate cursors and unsupported historical links are refused before Activity reads. Hidden Activity has no observer or timer; common shell/project reads retain their existing behavior.

Reuse panel/table boundaries, native pager buttons, safe text, copy link, source metadata and scrolling. No graph or permanent inspector in this slice. Phone text wraps with labeled dates/references; no discarded essential metadata or arbitrary vertical feed accumulation.

## Skills and verification

Use AEW frontend-design 0.3.0 and test-design 0.3.0; record identities and actual feedback separately. Tests derive expected results from the accepted schema/route and this presentation policy: first page50, replacement on Next, exact subject mapping, unavailable target, safe supplied reason, empty/capability withdrawal and invalid cursor. Observe the missing-interface red before implementing the new page; do not manufacture red by deleting working code.

Check compiled desktop/phone, both themes, keyboard/focus, copy/reload, long/hostile text, at least two pages and bounded row count. Verify manual reads, stale/refusal recovery and conditional responses at the actual transport boundary. Existing unit/browser regressions cover unchanged transport owners; targeted regressions cover this slice. Keep synthetic evidence distinct from actual live-server acceptance.

Run pinned Node22 offline gate, secret scan, production exclusion and applicable browser suites. Commit runtime before a clean detached exact-source freeze. Preserve build inventories, screenshots and failed trials. Independent exact-head review and current-head CI observation are required by AGENTS; normal merge gates apply.

## Remaining work

Worker Now and its optional graph are a separate checkpoint. The Lead line, notification tiers, new known-value vocabulary, mutable History semantics and live Settings integration require their respective accepted Engine inputs. No Engine work records or speculative API fields are created here.
