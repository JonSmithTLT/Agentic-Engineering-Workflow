# Independent STG-02 correction review

Head: af77308aa48cbc73a73791b58b807c0a9ebdbe55. Previous reviewed head: 3173362d2cc5f6dde2b49db7103092f903bd2760. Date: 2026-10-20.

Fresh reviewer context, separate from implementation. Scope: the whole delta since the previous reviewed head, F1–F4 and N1, and genuine related regressions. The intermediate 31c7c4350b533801d3bf27a77019a452d64befe8 had a null collection-basis dereference in the browser driver; the additional af77308a commit fixes that assertion and changes no runtime source. This verdict covers the latter commit only.

Read AGENTS.md, the initial review, website handoff, SLICE-FIELD-MAP, the adopted O-01 owner-read/Problem contract, D-01 representation constraints, selection-profile ownership/CS-03/CS-04/CS-08 rules and consumer directives. Authority is the selected sealed v0.5.4 archive, SHA-256 64e65578e9774fd9425c19ceaff30f1a0018ae819baa58d9469ed0c33e8f299f, extracted read-only under web/artifacts/stg02/adopted-v0.5.4. Candidate markers in selected files do not displace that adoption authority. No backend code, branches or private notes were inspected and no backend/person was contacted. Only this report was written.

A23 F01/F32/F03/F04 remain unwitnessed shape examples; their stamps are not semantic proofs. Witnessed F05/F13 do not qualify this deployment. Fixture bodies and the permitted designer driver are reference tooling, not owner-authority evidence.

## Exact-head CI observation

At 2026-10-20T19:29:55-04:00, with git rev-parse HEAD returning af77308aa48cbc73a73791b58b807c0a9ebdbe55, the reviewer requested:

`gh api repos/JonSmithTLT/Agentic-Engineering-Workflow/commits/af77308aa48cbc73a73791b58b807c0a9ebdbe55/check-runs --jq '.check_runs[] | {name,status,conclusion,html_url}'`

It failed with error connecting to api.github.com. No remote check names, run IDs, completion states or conclusions were observed. No PR was created as part of this review. Required assurance is NOT OBSERVED; attribution is UNKNOWN. Author-reported tests and concurrent pinned clean-source freeze are not independent acceptance evidence and are not adopted as CI qualification by this verdict. Review CLEAR does not qualify CI.

## Findings and nits

None at this head. All points that this pass would raise are included here; no optional points are reserved for later.

## Resolution of the previous findings

- **F1 closed.** Recovery now stores a versioned, validated immutable request plus disposition. All five terminal Problem codes remain non-retryable after remount. All other selected Problem retry prerequisites remain visible and blocked until their prerequisite can actually be established; this slice does not pretend to establish it. Both the dispatch guard and button enforce the disposition. A pre-send in_flight write precedes every initial submission and lookup. If persisting a terminal result subsequently fails, the durable in_flight marker survives and remount remains blocked. Owner-index navigation remains available. A genuine lost transport response still enables a deliberate lookup using exactly the original serialized body and client key, without automatic replay.
- **F2 closed.** Binding checks a run item's identity only when an item exists. Both schema-valid empty unavailable and unsupported envelopes render their supplied outcomes and limitations. A present wrong run identity still produces a binding refusal. Continuation's distinct one-item rule was not relaxed.
- **F3 closed.** After structural validation, owner, operation_ref and intent_ref must each agree between owner envelope and nested result. Route identity is checked separately. When a persisted receipt maps the exact owner-operation pair to a known original intent, request_set_ref, recipient_ref, installation_ref and intent_ref are also checked against the saved request/mapping. An unrelated pair is not assigned a guessed original request. These checks detect known contradictions; they do not fabricate or certify inaccessible owner-native evidence.
- **F4 closed.** List coverage now has its own aggregation-only source display, observation/qualification/validity information, inspectable full collection basis and per-owner closures. It is separate from item authority. Supplied final/empty bases are visible, while absent bases display Not supplied. Scoped completeness, incomplete membership and next-page wording remain distinct.
- **N1 closed.** WEB-STG02-002 now distinguishes completed author fixture/render work from pending designer triage and real source/currentness qualification, without claiming independent acceptance.

## What looks sound

- New read and command paths stay separate from provisional dashboard API views.
- No continuation axis enables command authority. Unknown remains explicit with its supplied reason/basis/time; G3 protected actions remain held text with no protected dispatch control.
- 202 still means received, with per-intent results in request order. A receipt does not establish an owner effect.
- Refused or contradictory owner representations never publish their effect heading. Nondisclosing 404 treatment remains unified.
- The browser-driver correction scopes its assertion to the collection section and accepts null collection_basis explicitly; it no longer treats a legitimate absent basis as an executable property dereference.

## Independent verification and coverage limits

Native Windows Node v24.19.0 was used with existing dependencies, with no downloads or Docker builds. Commands from web/: `node node_modules/typescript/bin/tsc --noEmit`, `node node_modules/eslint/bin/eslint.js .`, and `node scripts/generate-stg02.mjs --check` passed (9 operation schemas, 176 static validator functions). `node --check scripts/browser-stg02.mjs` passed at af77308a. The reviewed diff was checked with git diff --check. Native Node24 is outside the pinned Node22 Linux acceptance environment.

Independent read-only Node/jsdom probes transpiled current TypeScript in memory using TypeScript transpileModule, loaded the existing static validators, mounted the actual components with React Testing Library and supplied synthetic fetch responses. They wrote no runtime or fixture files. Results:

- Enumerated every selected O-01 Problem allOf code/retry/status branch (11 codes), submitted it, remounted recovery, attempted reconciliation, and asserted disabled control, retained retry text and exactly one POST: all passed. This covers the complete selected code enumeration at this revision, not unknown future codes.
- Injected Storage.prototype.setItem failure after the first pre-send write, returned unresolved_no_redispatch, restored storage functionality and remounted: durable phase remained in_flight, retry stayed disabled and total POST count stayed one.
- Changed each nested owner identity field independently to a different schema-valid value: all three rejected. A consistent known mapping passed; changing each of the four known-original fields independently, including changing nested intent to preserve internal consistency, rejected.
- Rendered both legal empty limited run envelopes: outcomes displayed with no alert. A present wrong run ID rejected. Remounted after genuine transport loss and deliberately reconciled: both POST bodies were byte-identical.
- Rendered index-first, index-last, index-empty, index-partial and waiting. Supplied collection bases appeared in the collection section; null bases displayed Not supplied. The final and empty specimens retain scoped wording; partial/continuing wording is not upgraded by the source display.

The first collection probe incorrectly dereferenced a null basis in its own assertion; a second assertion incorrectly assumed every absent basis required incomplete rather than continuing/otherwise supplied page wording. Both harness assumptions were corrected and affected cases rerun; neither is attributed to runtime code. The production browser-driver null dereference was separately fixed by af77308a and its delta inspected.

Author-added tests were inspected for discrimination but are not treated as independent acceptance. No fresh full real-browser, CSP, pinned clean-source acceptance, live backend interoperability, physical-device or production qualification is claimed by this review. Semantic outside-response owner qualification is not mechanically enumerable here; coverage rests on the explicit client-known identity joins above and preserves the existing unqualified fixture boundary.

Review: CLEAR at af77308aa48cbc73a73791b58b807c0a9ebdbe55
