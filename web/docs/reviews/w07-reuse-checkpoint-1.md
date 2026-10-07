# W07 supplied reuse trail — checkpoint 1 review packet

Frontend fixture acceptance: ACCEPTED after formal independent correction re-check on 2026-10-06. This is the first bounded W07-02 slice; W07-01 and W07-03–05 remain deferred. No accepted or existing provisional wire schema, dependency lock, production package baseline or Engine work record changes.

Latest correction target and evidence are recorded below under Acceptance corrections; the earlier sections preserve the initial checkpoint.

## Review target

Runtime commit: `fce8afe8bf254edf84136002ce4fa1cb63adabc3`.
Runtime tree: `a58487df695970a4c85dfaa2fda47775436efbe5`.
Plan digest: `aacafb000f412170b6424acdf1f4badb1d72ba9261f7369eb811871709651435`.
Presentation manifest digest: `810e924f4da685659fbad7ea586204aec07753b33784f1829333b59e5624ac56`.

Independent plan and fresh-context code reviews are CLEAR. The code review found a nested-reference return-position defect; it was fixed before the reviewed runtime commit. The author subsequently added the explicit provisional inspector label after compiled visual inspection; the corrected exact commit was independently rechecked CLEAR. These reviews do not constitute independent product acceptance.

## Product task for independent reviewer

Use only compiled product UI on desktop and phone. Do not inspect fixture source, developer tools or API bodies to substitute for completing the task.

1. Open demo Journal J-05 → Provenance → Context associations. Identify the supplied association, source, fixed snapshot, invocation, optional run and packet identities. Disclosure alone must not initiate packet reads.
2. Inspect the associated packet. Establish the exact item/reference identity and its supplied disposition, scope and source revision. Keep preparation, delivery acknowledgment, output citation and benefit evaluation distinct. Identify what is absent versus what is explicitly supplied.
3. Follow a packet Journal reference, then browser Back. Navigate inspector tabs and return to Journal. Record whether the originating disclosure/control, selection and position are restored on both layouts.
4. Inspect canonical references, copy/reload the pinned inspector link, and use its explicit Journal return. Demonstrate that inclusion or acknowledgment is not evaluated benefit or proof of influence. Contrast with the earlier Retry packet, which excludes the later-published J-05.
5. Record identities, steps, outcomes, usability failures and disposition in a new review artifact. No completion-time target. Do not claim a complete reuse history or admitted Knowledge identity from this presentation fixture.

## Frozen evidence

Clean detached source/build evidence: `web/artifacts/commit-freeze/run-fO8kV3w5`.
Builder: `sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b` (Node22.22.2/npm10.9.7, Linux/amd64 glibc).
Browser runtime: `sha256:b9a4d7136af7f4fecd3848d0ebc1f3c84ad7fb3811f6434211928d8d110e4352`, Playwright1.59.1/Chromium1217.
Production inventory digest: `0a0925268c7992a42e9a3fbb0351c52343c8edbeeff824aba5a141298f72dc1a`, byte-identical to the merged baseline.
Demo inventory digest: `46a2df0a3b33238645dcde17a1685c5e8064ee9cfa6dc0f1a3fb144f363328cd`.

Pinned offline gate PASS: npm dependency tree, accepted/preview artifacts, documentation, generated accepted types unchanged, typecheck/lint, 4 live-input tests, 171 unit/component tests, both builds and production exclusion. Premium strict audit has zero findings. Existing canonical preview digests remain unchanged.

Commands: `SPT_FRONTEND_IMAGE=<immutable builder> bash web/scripts/freeze-committed-build.sh <full runtime commit>`; compiled browser scripts `ci-browser`, `browser-w02`, `browser-w03`, `browser-http-demo`, `browser-w04`, `browser-w05`, `browser-w06`, `browser-w07`, and `verify-live-runner`. Both fixture adapters are exercised; HTTP contexts block service workers. Supplemental command scripts, logs, screenshots and complete manifests are retained with the evidence bundle.

Final exact-commit browser regression PASS: nine suites, 126 checks, including seven unmodified authenticated-runner checks against its test adapter. Source stayed clean; production and demo inventories were unchanged afterward. Desktop/phone HTTP and worker screenshots are in `browser-output.tar.gz` under `output/playwright-w07/`. Supplemental keyboard/Enter/Home/End, light/dark and 390/720/1440px checks passed; three screenshots and `measurements.json` are retained separately.

An earlier exact-source run at ef6359b passed W01–W07 and six live-runner cases, then failed the report-write negative-control assertion. Two isolated diagnostic repetitions passed all seven cases; no production defect was reproduced. Retain the failed log. Do not claim its cause was proven. The final unmodified regression rerun must be recorded separately.

The Journal measurement initially observed +12 DOM nodes and the same five initial API requests as the frozen merged baseline. Inspector navigation adds explicit source/item/packet reads, not a timing improvement. Final measurement values and source identity are in the evidence bundle. Component tests verify one retained item page, validator removal on departure and cleanup on unmount. 720px reflow approximates 200% desktop zoom; physical devices and real browser zoom are not claimed.

## Authority and adoption

Prepared context, delivery acknowledgment, output citation and evaluated benefit remain distinct. Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.

Backend/live adoption remains separately pending; see [backend questions](../reference/backend-questions/w07-backend-question-ledger.md). The approved packaged frontend remains its agreed baseline until a separate source agreement, rebuild and live gate. The deferred page-density review remains on the register.

## Acceptance corrections — 2026-10-06

The independent main-line review of initial head `fa7e065` requested three minor presentation corrections while confirming the investigation, stage separation, chronology and navigation. Formal re-check subsequently accepted the corrections at `b7a7167`; see the acceptance record below.

Correction commit: `a7d972c67de9a8e555c115dca3744af918c30706`. Final verification commit: `cf7df4508c06397a280520015281661dafb39d2e`, tree `fe93b9a1b6e547299fb182d74a329ee5590d670e`. Subsequent runtime-checkpoint commits change browser-test synchronization only; their runtime builds match the correction exactly.

- The association host supplies presentation context to the shared inspector: association `ASSOC-J05-Later`, originating Journal item `J-05`, packet item `PKT-Later-J-05`, and scenario `later-ticket`. This remains visible on direct links and every inspector tab. Contents and Selection mark the exact matching item; a filter may hide its card while the header retains its identity.
- The shared packet header labels Source, Invocation, Run and Snapshot in definition-list rows.
- Demo-only identity tokens keep short identifiers together and bound long tokens to the viewport. No production stylesheet, wire schema or binding-validation change is introduced.

A fresh-context independent correction review is CLEAR at the final verification commit. Its scoped frozen-preview checks passed at 1092×844 and 390×844 in Edge 154.0.4258.53: exact context, one card marker, labeled identities, direct Receipts restoration and no horizontal overflow. A 500-character identity also fit a 290px containing block. These are three-finding checks, not a replacement for the original reviewer's full acceptance disposition. No physical devices or screen-reader coverage is claimed.

### Recovered and regenerated evidence

The original author checkout and raw browser captures were deleted. They remain unrecovered. The original reviewer independently rebuilt `fce8afe` and matched both original inventories; a later author restoration did the same. New correction evidence is generated from a clean detached committed tree rather than relabeling the old evidence.

New freeze: `web/artifacts/commit-freeze/run-Rwv6U0cX`. Pinned builder unchanged: `sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b`. Offline gate PASS, 171 unit/component tests and four live-input checks; artifact/docs/typecheck/lint, both builds and production exclusion PASS. Premium strict audit: zero findings.

Production inventory remains `0a0925268c7992a42e9a3fbb0351c52343c8edbeeff824aba5a141298f72dc1a`, byte-identical to the earlier freeze. Corrected demo inventory: `78d52d6ccae62029ff7c155a483b16b9a3adcf86a7db333d50fc04a424c7d17a`.

The previous Chromium 1217 installation was deleted. The browser carrier remains `sha256:b9a4d7136af7f4fecd3848d0ebc1f3c84ad7fb3811f6434211928d8d110e4352` with Playwright 1.59.1; this correction run uses the installed Chromium 1247 through `CHROMIUM_PATH`. Executable SHA-256: `adf078f8f80eb9e980a07b4418af23b0f4008a83bc5756d5588055bc4d76c5a0`. This runtime difference is disclosed rather than claimed identical to the original browser evidence.

Two earlier runs at `a7d972c` timed out in the existing phone Work HTTP keyboard test. The test could focus a child before the preceding two-animation-frame Results focus restoration completed. An isolated diagnostic passed after awaiting that existing focus contract. `fe6dacb` adds that explicit wait before the next keyboard action; every detail-heading/Back/visibility assertion remains intact, with no product change. Original failed logs, the second failure capture and diagnostic are retained in the earlier correction freeze `run-a17Zk4FO`. An independent Edge probe passed both original and synchronized workflows; it does not prove why the original Chromium run failed.

The next full attempt at `fe6dacb` passed W01–W05 but failed the W06 manual-read counter by one request. The event heading appears before its dependent execution read; the copied-link test previously began counting at that early heading. An isolated diagnostic awaiting the existing Captured execution heading passed all four HTTP/worker desktop/phone story paths. `cf7df45` adds that wait, matching the existing `pick` helper and preserving the full 11-second no-new-reads assertion. No product polling behavior changes. Failed logs/capture and diagnostic are retained in `run-Qro2jQUa`; an independent Edge check also observed unchanged request counts at both widths after this boundary.

Final exact-commit regression PASS: nine suites / 126 checks, including the seven authenticated-runner test-adapter checks. Worker and HTTP paths passed; HTTP blocked service workers. W07 exercises the 1092px desktop width and 390px phone layout, exact association/card identity, labeled header, copied links and return focus. Source remained clean and both complete build inventories were unchanged after the run. Browser logs, output archive, command copies/hashes, premium report and scoped independent review are retained with the final freeze. These checks do not establish physical-device, real-zoom or live Engine acceptance.

### Formal re-check task

Repeat the original desktop/phone association flow and direct Receipts link. Establish the association and exact packet-item ID through the visible UI, find its marked card, read the four labeled header identities, and confirm `SNAP-Later` stays together at the original desktop width. Check return navigation still restores the original position. Record the reviewed source/build and acceptance disposition separately; backend adoption and live integration remain pending.

## Formal frontend fixture acceptance — 2026-10-06

The independent AEW main-line reviewer appended a formal re-check of PR head `b7a7167aa37deb46947faf355bbbda545fded92b`: **ACCEPTED, all three findings fixed, no new findings**. Reviewed verification source `cf7df4508c06397a280520015281661dafb39d2e`, tree `fe93b9a1b6e547299fb182d74a329ee5590d670e`, and runtime correction `a7d972c`.

The reviewer compared the served demo to the new freeze: 32 of 34 files were byte-identical; the HTTP transport meta tag and blocked service-worker response explain the other two. The reviewer inspected the source diff and completed visible-UI checks at 1092×844 and 390×844, with rendered-DOM reads for focus, scroll, line boxes and overflow.

Both layouts passed association context on direct links, the exact matching item marker, Source/Invocation/Run/Snapshot labels, unbroken identifiers without horizontal overflow, and reference/Back/Journal return restoration. The reviewer reported no new findings. This accepts the first bounded W07-02 frontend fixture slice only; it does not complete the wider W07 milestone or adopt a backend projection.

Limitations: emulated layouts in one desktop browser; no physical devices or real zoom. Long-content fixtures were not re-exercised in the formal re-check; author coverage remains separate. The reviewer did not rerun the author's correction gate or browser suites, relying on retained freeze logs and served-file verification for that evidence. The original author screenshots remain unrecovered. Backend adoption and live integration remain pending; the production package baseline is unchanged.

Source artifact: `w07-review-main-line.md`, supplied by the operator and retained with the local review handoff. Artifact SHA-256: `ec680140454d5f4e3821a23a93607597fba5f385b6c08d382248c003be7a88e3`. This repository-relative summary preserves its disposition and limits without introducing machine-specific checkout paths.
