# W05 independent review packet

Frontend fixture acceptance is **ACCEPT at e875e81**. Backend adoption and live integration remain separately pending. W04's merged acceptance is preserved. No Engine work records were created. Current disposition is recorded in `web/docs/w05-frontend-acceptance.json`.

Update 2026-10-04: the reviewer independently rebuilt `e875e81b417738dfaa9a43990ebfd330db795094`, verified all four fixes on both layouts and recorded ACCEPT, conditional on correcting the evidence provenance. The prior working-tree evidence was incorrectly attributed to the later commit and is superseded. Current evidence in `web/docs/w05-review-fixes-evidence/` was regenerated from a clean detached checkout of that exact commit; the offline gate and 25 browser groups passed, and source/build hashes remained unchanged afterward. This fulfills the recorded condition. The independent report is `web/docs/w05-independent-review/w05-review-main-line.md`.

The approved plan is `web/docs/design/plans/w05-evidence-inspection.md`; operator approval is recorded against its SHA-256 in `w05-operator-approval.json`. The immutable implementation commit, preview digest, commands, screenshots and measurements are recorded in `web/docs/w05-evidence/result.json`. Review that source commit; the evidence commit changes documentation only.

## Run the reusable preview

From `web/`, use the pinned Node 22 runtime to run `node --experimental-strip-types scripts/demo-server.mjs`. Set `DASHBOARD_PORT` to an available port if necessary. This serves the compiled demo and shared HTTP fixture projectors, including Journal, Investigation and Evidence inspection. It requires no service worker. Build with the pinned offline gate first if `dist-demo` is unavailable. The worker adapter remains supported and tested separately.

Start at `/knowledge?fixture=F1&view=journal&selected=J-05&panel=evidence`. Repeat the investigation independently on desktop and at a 390px phone viewport. Use only product UI; fixture source, developer tools and Contract Playground cannot substitute for discovering the requested identities and results. There is no completion-time target.

The local immutable builder lives in Ubuntu WSL's native Docker, accessed through `/snap/bin/docker`, separately from Docker Desktop. From the repository root inside Ubuntu WSL, run `PATH=/snap/bin:$PATH SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 bash web/scripts/offline-gate.sh`. The pinned build uses `--network none`; a networked npm install is unnecessary when this image is present.

The HTTP projector's `stale` and `refresh-error` scenarios intentionally retain failure state across browser sessions. Restart the demo server before independently exercising their initial successful load followed by failed refresh. A fresh browser session alone does not reset that server state.

For evidence freezes, run `bash web/scripts/freeze-w05-evidence.sh <full-source-commit>` from the repository with `SPT_FRONTEND_IMAGE`, absolute `PINNED_NODE22` and `CHROMIUM_PATH` set, and the required browser runtime libraries available. This creates a separate clean committed checkout, runs the pinned offline gate and W05 browser suite inside it, then verifies the source and every build file stayed unchanged. `scripts/freeze-committed-build.sh` provides the build-only form. Use the emitted checkout's browser output and build provenance when archiving evidence; do not substitute an existing working-tree build or its screenshots.

## Required investigation

1. Open J-05's supplied supporting reference CLANGD-E871. Record its reference association, then explicitly select the authorized fixed source. Inspect Record, Artifacts and Provenance. Establish what the removal diagnostic actually reports, its canonical references and source/snapshot identity.
2. Select ART-Removal. Record artifact revision, supplied full-artifact digest, displayed byte/line range and verified excerpt digest. Copy a citation and reopen its pinned dashboard link. Confirm it names the same source, artifact, revision and range and contains no artifact body. Distinguish excerpt verification from full-artifact integrity and claim truth.
3. Return to the originating Journal using Back to originating investigation. Record whether selection, tab, scroll and originating-link focus are restored. Repeat for supporting CLANGD-E875 and opposing CLANGD-E880; establish what refreshed compilation evidence and the opposing diagnostic say without turning the evidence role into a browser-generated conclusion.
4. Open `/compare?fixture=F1&a_source=SRC-Removal&b_source=SRC-Retry`. Explicitly select any run needed for the investigation; no run is chosen implicitly. Record invocation, run and fixed source/snapshot identities, reported removal/retry outcomes and available receipt stages. Inspect PKT-Retry's supplied CLANGD-E875 reference, then return to its originating packet. The discovery source precedes the retry and J-05 is published afterward; the earlier packet must not contain J-05.
5. Compare what you inspected with the recorded successful retry. Explain what the supplied records establish and what remains unknown. Excerpt coverage, inclusion, delivery acknowledgment, output citation and evaluated benefit are distinct; neither the diagnostic nor a retry outcome proves causal benefit.
6. Inspect the later-ticket packet and missing benefit evaluation. Demonstrate that including J-05 or acknowledging delivery does not establish benefit. Record canonical references as references to their authoritative records.
7. Exercise phone List/Detail switching, selected artifact identity, keyboard tabs, Back, copied-link reload, both themes and 200% zoom. Use the Evidence scenario selector for incomplete, unavailable, denied, unsupported and integrity-failure results. Confirm that unavailable mappings do not resolve by Evidence ID resemblance, and hidden or rejected content is not shown.

Useful expected fixture locators (these identify the task, not its answers): `REF-J05-CLANGD-E871`, `REF-J05-CLANGD-E875`, `REF-J05-CLANGD-E880`, `REF-PKT-Retry-E875`; sources `ES-Removal`, `ES-Discovery`, `ES-Counter`; artifacts `ART-Removal`, `ART-Discovery`, `ART-Counter`. The same canonical Evidence ID can have multiple independent association identities. Do not treat Evidence ID as a resolver key.

## Record the review

Use `web/docs/w05-review-main-line.md` or another committed review artifact. For **each layout**, record starting URL, source commit/digest, invocation/run/source/snapshot/packet/reference/Evidence/artifact IDs, investigation steps, observed results, citation identity checks, canonical references, receipt availability, return/focus behavior and usability failures. Record PASS/FAIL and findings for each required task, then an explicit frontend fixture disposition. Reviewer identity and review date must be factual.

Implementer automation is supporting evidence, not independent acceptance. A reviewer ACCEPT does not adopt the provisional backend contract or establish live integration.

## Capability and adoption boundaries

W05-02 records that accepted API 0.1.2 lacks lifecycle transitions and the Evidence CLI provides ingestion rather than read-only `show`. No Timeline or speculative CLI command was added. W05-03–04 benchmarks remain deferred. Evidence identity and ownership are unchanged; future Knowledge Capture & Admission records reference existing Evidence.

Backend questions remain in `web/docs/design/w05-backend-question-ledger.md`, including association authorization, immutable retention, original-byte/range/digest semantics and live adoption.
