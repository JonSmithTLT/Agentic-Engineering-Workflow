# W07 supplied reuse trail — checkpoint 1 review packet

Frontend fixture acceptance: PENDING independent desktop/phone product review. This is the first bounded W07-02 slice; W07-01 and W07-03–05 remain deferred. No accepted or existing provisional wire schema, dependency lock, production package baseline or Engine work record changes.

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
