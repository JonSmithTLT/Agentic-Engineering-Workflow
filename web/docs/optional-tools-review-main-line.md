# Optional Work graph and developer tools: main-line review

| | |
|---|---|
| Reviewed | `7c120b4..7e13f34` on `feat/aew-dashboard-work-graph`: the Work graph (`a4eef03`, `5fe7d61`), the developer tools (`8c3ca29`) and the header polish (`7e13f34`) |
| Claims read | `optional-developer-tools.md`, `validation-work-graph.md` |
| Contract and lock | Unchanged at `7e13f34`: contract 0.1.2 and `package.json` and the lock file have no diff from `7c120b4` (verified) |
| Reviewer, date | Claude, the main AEW agent, 2026-10-03 |
| **Disposition** | **ACCEPT, with one Low finding (OT-1) to fix before these changes merge to `main`.** It is small and can land on the W01 line, which builds on this one. |

## How this review was done

Static review of the committed diff, read through `git` from the main repository. I did not run the offline gate or the browser scripts: the 85 tests and the browser checks are the frontend's evidence. Read in full: `api/transport.ts`, `api/diagnostics.ts`, `api/cli.ts`, `main.tsx`, `client/view-memory.ts`, `components/SinceViewed.tsx`, `CopyCli.tsx`, `JumpToId.tsx`; `LineageGraph.tsx` for its fetch bounds and expansion rules; `DeveloperPanel.tsx` for unsafe rendering. The Work graph was checked for what it fetches, not for layout.

## What I found sound

- **The CLI commands are real and read-only.** `aew work show`, `aew invoke show` and `aew history show` exist (`cli/work_commands.py`, `cli/history_commands.py`), and archived records resolve through them (ADR-0011 R7, P2c). Audit ids (`AU-n`) are history records. Evidence gets no command, which is right: there is no `evidence show` yet (register E12). The ID allowlist (`^[A-Za-z0-9][A-Za-z0-9._-]*$`) cannot start with `-` and carries no shell metacharacters, in POSIX shells or PowerShell. Nothing is executed.
- **The request log is observational.** It is in memory, bounded to 200 entries, and keeps no headers other than ETags, no cookies and no bodies. Transport behaviour is unchanged: the 304, abort and cache order is the core's, and the log is written in a `finally`. The two ETag observations are labelled as browser observations, not as server health.
- **"Since you last looked" stays a convenience.** Storage is read and written only inside `try`, validated with a schema, bounded (100 items, 20 scopes, 2 MB read cap), keyed per project and view, and remounted when the scope changes (keys in `Work.tsx` and `ProjectionViews.tsx`). It reports "new to this loaded page", never deletions or completions, and it does not overwrite a newer saved revision. This is the per-viewer use of browser storage I asked for.
- **The lineage graph is explicit and bounded.** It expands only on request, at most three levels deep, 24 cards and 80 links, through the existing validated transport and query cache. It routes relations the FR-1 way. An `audit_finding` target is a History node, which settles the earlier FR-1 note.
- **Jump to ID** validates the ID and checks the capability before it navigates, and it makes no request of its own.

## Finding

### OT-1 (Low): `beforeunload` detaches refresh even when the page does not unload, and blocks the back-forward cache in Firefox

`main.tsx`. The fix for the demo's intermittent 404s cancels queries and detaches the visibility and focus handlers in a capture-phase `beforeunload` listener, and reattaches them on `pageshow` only when the page is restored from the back-forward cache.

- **`beforeunload` is not unload.** It also fires when a navigation does not complete: another listener cancels it, or the target is a download or an external protocol handler. The page then stays open with refresh-on-focus and revision catch-up switched off until it is reloaded. The interval polling still runs, so this is degraded, not stuck.
- **A `beforeunload` listener makes the page ineligible for Firefox's back-forward cache**, so the `pageshow` restore path rarely runs there.
- **It is in the production build too**, although the problem it fixes (the demo service worker deactivating under an old document) is demo-only.

**Fix:** use `pagehide` instead of `beforeunload`. It fires only when the document is actually being hidden for navigation or unload, it works with the back-forward cache, and the existing `pageshow` (with `persisted`) restore pairs with it. Optionally keep the cancellation demo-only.

**Retest:** the existing demo navigation and reload probe (no 404s); a blocked navigation leaves focus refresh working; a back-forward restore refetches active projections.

## Notes (not findings)

- **"No response bodies are retained" holds in substance.** One nuance: a Zod issue message can quote the received value, for example an enum's unexpected string. Such quotes are short, kept in memory only, and are data the page already displays. No change is needed; the packet could say so.
- **Ctrl/Cmd+K replaces the browser's own shortcut** (search-bar focus) on every page. That is common practice for command palettes, and the header button is the alternative.
- **The saved scope includes the opaque cursor.** It is harmless, but it means a later page of the same list is a separate comparison scope. That's as intended.
- **The storage boundary is wider than the accepted core's theme preference**, as the packet says. I accept it as a per-viewer convenience. It must never become a source of truth, and nothing here makes it one.

## Gate

When OT-1 is fixed, I accept a diff limited to it without another full review. Graph-wide traversal, relation overlays and a lifecycle timeline still need main-line projections and a renewed contract review (register F20).
