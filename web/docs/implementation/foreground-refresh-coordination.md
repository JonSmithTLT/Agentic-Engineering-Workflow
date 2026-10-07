# Foreground refresh coordination

The visibility and focus callbacks could restart the same pending automatic refresh. A bounded coordinator now shares that pending read for each active query during the same foreground episode. The first wake still supersedes an older read; hiding or blurring permits a new wake to supersede it again. Explicit manual refresh, session retirement, transport validation and revision reconciliation retain their existing owners.

This is a frontend-owned request-coordination change, not a freshness expiry rule or backend contract. There is no time debounce. A settled read does not suppress a subsequent refresh, and newly active/replacement query objects are independently eligible. Fixed/manual-only and concealed projections retain their exclusions. Disposing the listener removes its tracking.

## Measured decision

Baseline is merged `1c96281f45a43a696b7635ea444a2949bdbbdfc1`; implementation starts from merged `d1bf46cacde391a13ae638cd015e7655540b8613`. The query coordinator's baseline Git blob is identical in both commits (`d7a3e01eb335d0348ef88cc07ec2dfcee08c22a5`). The earlier startup improvement is not credited to this experiment.

Three matched instrumented trials use actual useProjection and ReadTransport with schema-valid accepted F1 data. After a valid initial read, hold refresh responses and issue visible-document then focus callbacks:

| Per trial | Baseline | Candidate |
| --- | --- | --- |
| Refresh adapter requests started | 2 | 1 |
| Superseded adapter requests aborted | 1 | 0 |
| Surviving valid 304 reads completed | 1 | 1 |
| Payload identity and represented generation preserved | yes | yes |

Six compiled HTTP-demo trials (three each at 1092px and emulated 390px) observe two conditional request starts before and one after. All observe a 304 response, retain the Overview heading and record no page errors. Chromium also emits aborted notifications for these intercepted conditional requests; those notifications are not used to infer distinct cancellations, successful body completion or server processing counts. The instrumented adapter supplies the abort/completion counts above.

The baseline holds the first request until the companion request is observed. The candidate instead acknowledges the companion event through two animation-frame turns before releasing its single request. Both deliberately keep the first read pending; the candidate cannot wait for a second request it should prevent. This is a controlled event-sequence experiment, not a frequency measurement of natural browser events, live Engine traffic, physical-device performance, latency comparison or production savings claim. No timing SLA is introduced.

**Triage: IMPLEMENT NOW** for the demonstrated bounded reduction, subject to final-head review and applicable assurance. Arbitrary cache eviction remains deferred: the independent lifetime probe shows conditional reuse and scope teardown, but its serialized payload-size proxy is not physical heap pressure.

## Frozen evidence

Runtime commit `9062219ea0b9c2cb9468a5c5f3f01dcb736d1c1b`, tree `d27f894e78976d046f8a8d4d689506b58367aa08`, clean detached freeze `web/artifacts/commit-freeze/run-waj2SODy`. Pinned Node22 offline gate passed 179 tests and both builds. Builder `sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b`. Production inventory digest `ba92c615f98d6f0350fdf1ec8ad93f8dae7c9b6a9ed93fa725a93241c61313f9`; demo `8baba655ccbd655bf717ef35c148edab708fd7b7ac46477f4f115a3854ad9048`. This runtime intentionally changes current production assets; the agreed packaged F20 baseline is untouched.

Raw evidence SHA-256:

- baseline instrumented samples: `5d69bd18347d5693b7acd06765ff1e2119dcac59276d0fcdc4f286736ebd7cad`;
- candidate instrumented samples: `21398327a4093fc80598d3c8beb5c2d127f35a0ddcfee0a06139bd1a4b660ac8` (three overlap trials; nine retention tests explicitly skipped, not claimed rerun);
- baseline compiled samples: `f8404aa7ed393dbdc6aed277912d1c0182104043c38a5ed68b4c71f72b697b2a`;
- candidate compiled samples: `3c16c8cd952961cc6a6f8d68c9f89dd7ae34a500995a24937041c22e71f95799`.

Probe scripts, original failed setups, complete logs, screenshots and manifests are retained with the local workstream evidence. Six coordinator regression cases cover companion sharing, fresh episodes, manual cancellation both ways, stale finalizers, excluded/new queries, disposal and same-key replacement ownership. Existing transport and browser gates separately cover stale/refusal/obsolete/304 behavior. Independent code review is CLEAR at the runtime commit, without claiming independent execution or live acceptance. Final documentation-head freeze, complete browser results and current-head review must be recorded separately before merge.

Accepted and provisional wire contracts, generated accepted types, dependencies, authorization semantics, polling intervals and preview exclusion remain unchanged. No Engine records or backend requirements are introduced.
