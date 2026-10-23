# STG-02 website corrections and joint-test handoff

Date: 2026-10-20. Author verification, not joint acceptance.

## Exact runtime and review

Runtime/test checkpoint: `af77308aa48cbc73a73791b58b807c0a9ebdbe55`, tree `9c92ff8a1479fc9b13633dbf5436354ed93441ec`. The adopted sealed v0.5.4 archive remains SHA-256 `64e65578e9774fd9425c19ceaff30f1a0018ae819baa58d9469ed0c33e8f299f`. No adopted bytes, existing dashboard contracts, dependency lock or backend implementation changed.

The [fresh independent review](reviews/review-af77308a.md) closes F1–F4 and N1 from [the first review](reviews/review-3173362.md), with no new findings or nits: **Review: CLEAR at af77308aa48cbc73a73791b58b807c0a9ebdbe55**. This is an implementation review, not owner-source qualification or joint acceptance. No PR or remote assurance was observed for this local checkpoint; it is not described as CI green.

| Point | Correction | Verification |
| --- | --- | --- |
| F1 — retry directives and reload | Exact serialized request, recovery phase and validated Problem guidance persist together. All five `never` codes stay terminal after reload. A pre-send non-retryable marker prevents a failed post-response storage write from re-enabling dispatch. Other prerequisites are displayed without claiming fulfillment. | All five terminal classes in component and compiled-browser reload checks; all four nonterminal guidance classes; failed terminal persistence; genuine transport-loss exact-byte lookup; independent probes |
| F2 — legal empty limited runs | Empty unavailable/unsupported responses render their envelope. Present wrong identities still reject. | Both legal states and a wrong-present-identity control; compiled desktop/phone limited-state checks |
| F3 — contradictory owner identity | Reject redundant nested owner/operation/intent mismatches. Match known original request-set, intent, recipient and installation through the persisted exact receipt mapping. | Individual and combined nested contradictions; four known-origin contradictions; valid specimen and fixture HTTP journey; compiled positive outcome and negative contradiction |
| F4 — collection basis | Show collection provenance beside scoped closure, separate from item authority; disclose per-owner closures. Null basis remains explicitly unsupplied. | Waiting and first/final/partial/empty index specimens; scoped empty component check; desktop/phone captures |
| N1 — stale gap status | WEB-STG02-002 now records author fixture/rendering work complete while designer triage and real qualification remain pending. | Independent wording recheck |

## Frozen evidence

Clean detached source at the exact runtime commit was built with the offline pinned image `sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b`, Node 22.22.2/npm 10.9.7, network disabled. Gate **PASS: 259 tests**, artifact/schema checks, typecheck, lint, all three builds and existing production exclusion.

Freeze: `web/artifacts/commit-freeze/run-ef8dde21`. The complete build manifests, provenance, browser summary and post-browser verification are copied to [evidence/af77308a](evidence/af77308a/provenance.json).

| Build | Files | Complete manifest SHA-256 |
| --- | ---: | --- |
| Existing production | 8 | `fcb7b25b16508cfe419528e07bca83adc188fbc4ab2b1b44148106113319dcd9` |
| Existing demo | 43 | `2b20749e478f63e533b0a90b99f0562197d2d2982a9be122c8b435695eac090d` |
| Isolated STG-02 | 4 | `d6ec95cf93b42beb4a3902039a104734e3c3d1289f023f0be7fd55659b0608a1` |

Existing production/demo manifests are identical to the first `3173362` freeze. The STG-02 build matches the preceding corrected runtime `31c7c435`; the intervening commit fixes only the browser driver's null-basis assertion.

The frozen checkout's `browser-stg02.mjs` ran against its own pinned output using `STG02_WEB_ROOT=web/artifacts/offline-gate/dist-stg02`, `STG02_SPAWN_FIXTURES=1`, a loopback-only `STG02_BASE_URL`, and explicit local `CHROMIUM_PATH`, `STG02_PYTHON`, `STG02_DESIGNER_DRIVER` arguments. These paths are operator-local inputs, not committed machine paths. The harness owned and stopped its finite-lifetime fixture processes. This run used no real session or credentials.

Headless Edge checks **PASS at 1440×1000 and 390×1000**, with service workers blocked: fixture HTTP waiting → run → continuation → deliberately selected C17 command → 202 → exact owner GET/reload; recorded full/partial/stale/scoped list states; nondisclosing 404 and 503; legal empty limited run responses; contradictory owner rejection; and each of the five terminal Problem codes before/after reload. No page script errors were observed. The author visually inspected [phone scoped-empty provenance](evidence/af77308a/390-index-empty.png) and [desktop terminal recovery](evidence/af77308a/1440-terminal-unresolved_no_redispatch.png). Additional captures include [phone unavailable run](evidence/af77308a/390-empty-run-unavailable.png) and [owner binding rejection](evidence/af77308a/1440-owner-binding-rejected.png).

After browser checks, native Git confirmed the detached source remained clean at the same commit/tree; every file/count/hash in all three build manifests was rechecked and unchanged. See [post-browser-verification.json](evidence/af77308a/post-browser-verification.json).

Failures remain preserved: the first baseline regression run; its corrected schema-valid unsupported specimen; the Windows native dependency setup failure; and `run-11d58d94/browser-stg02.log`, where a driver assumption dereferenced null `collection_basis`. That last failure was corrected in the driver at `af77308a`, not hidden or attributed to the backend. The full gate was regenerated and the final compiled suite passed. No broad inherited browser-suite rerun is claimed for this isolated correction; existing production/demo bytes did not change. No real zoom, physical device, live owner authority or backend interoperability is claimed. The isolated static-validator bundle size warning remains disclosed.

## Joint test next

Author fixture corrections are complete. Joint testing has **not started**. Use the exact frozen runtime above, not a working-tree rebuild. The website remains a separate `/stg02` entry; it has not replaced the existing dashboard.

The joint setup needs the backend's test base URL/serve arrangement, exact backend source identity, and explicitly supplied synthetic recipient/installation/work/run/delegation bindings. No implementation notes or backend source inspection is needed. The adopted headers, no-store behavior, deliberate separate request and exact owner-operation identity remain the integration boundaries. Real credentials and operator sessions remain outside this fixture test.

Walk through waiting → supplied run → information-only continuation → separately delegated deliberate Continue → 202 received/not done → reload → owner index/exact owner observation; verify held G3 text without protected controls. Include unknown effects, partial/null collection basis, source unavailability and terminal reconciliation. Record sanitized mismatches in [JOINT-TEST-NOTES.md](JOINT-TEST-NOTES.md) and classify gaps before changing an interpretation. No witness-less fixture stamp becomes a guarantee simply because the views render it.
