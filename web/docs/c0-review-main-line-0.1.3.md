# Independent C0 review: Dashboard API 0.1.3

**Disposition: C0 ACCEPT. No mandatory findings.**

Reviewed on 2026-10-10 by a fresh-context independent reviewer (R1), separate from the implementation author and without the author's reasoning. Repository `AGENTS.md` applies. Repository source context: `60a26c398dfd37dd2e5101d4e4ab09633838db99`. This verdict identifies the exact contract artifact by digest because the review precedes its commit.

- Final target: `docs/design/dashboard-api-v1-provisional.yaml`, version 0.1.3, SHA256 `417fa77739a006d65605737794efa6b957c68b6cecd9f6a4d0fd1869272187fb`.
- Baseline: `tests/fixtures/dashboard/contract-0.1.2.yaml`, SHA256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`.
- Authority: merged `docs/design/proposals/dashboard-maps-and-history-search-v0.1.md`, Appendix A and surrounding guarantees, SHA256 `8ab1629fb54c20214a98f482c1fe6924bdd62ea9ccadedbf36fcc9ad07ff7822`.

## What looks sound

- All 16 existing paths and 56 existing schemas retain wire compatibility. Existing GET/HEAD operations, responses, parameters, bounds, authentication and 0.1.2 response envelopes are unchanged. `Capabilities` gains only the two allowed optional `Capability` references, `maps` and `history_search`.
- The parsed contract equals 0.1.2 plus all eight Appendix A blocks after stripping descriptions and extensions. The permitted `Integration.status` known-value annotation adds `integrated`; no strict enum, bound or served shape changes.
- Exactly six paths are added: `/maps`, `/maps/structural`, `/maps/structural/{root}`, `/maps/structural/{root}/inputs`, `/maps/diff`, `/history/search`. GET/HEAD parameters, status sets and ETag definitions match; HEAD responses contain no payload. New envelopes carry 0.1.3. All references resolve and JSON Schema components and parameters compile.
- Maps use SHA256 roots and full lowercase object IDs for comparisons. Pattern probes reject traversal/absolute paths, options, refs, short IDs and uppercase IDs. Maps remain bounded derived navigation context with labels, freshness, omissions and typed item allowlists. Repository-relative paths are data, not arbitrary file-access inputs; no storage layout, registry actor/log or credential field is introduced. Requests never generate a map.
- Search remains conditional on the adopted execution-policy authority described in the merged proposal. Capability absence means not offered, suppressing requests rather than becoming UNKNOWN. Operator cookie authentication remains inherited; off-state authenticated fallback and no recall-storage access remain implementation obligations. Declaring the route does not claim it is deployed.
- Search responses preserve authenticated historical records, reference/trust labels, inert credential-redacted plain-text snippets, collision-free fences, coverage reasons and typed argv/entity expansion. Search is separated from admitted Knowledge and carries no arbitrary href/storage or new credential surface. It is explicitly user-initiated, never polled or performed while typing.
- Main-line compatibility stripping preserves field names such as `description` and `x-user`; executed change/removal probes fail correctly for those property names. Existing implementation/tests cover route removal, HEAD removal, parameter changes, new required parameters, response changes, bounds and the narrow capability exception. Pending routes are derived; S0 serves none of these additions yet.

## Verification and final recheck

Initial independent acceptance reviewed SHA256 `0b6ee339fac729c9f19f7226a494d30f5a27c753942a6668606371a359d8be80`. A final exact UTF-8 parsed comparison found only `x-c0-review` changed: ACCEPTED status, amends 0.1.2, the current review-document reference and updated notes replace stale 0.1.1 bookkeeping. Every other key/value, including all authority annotations and additions, is identical to the initial reviewed document.

The independent structural probe passed against the final artifact: full Appendix A equality after annotation stripping, all old schemas/operations, GET/HEAD parity, reference resolution, identifier rejection examples and property-name preservation. Normal execution of `aew.dashboard.contract.compatibility` against all baseline paths and `compile_problems` returned no problems.

With the reviewed repository's `src` on PYTHONPATH:

```sh
python -m pytest tests/unit/test_dashboard_contract.py tests/unit/test_dashboard_contract_note.py -q
```

Result: **57 passed in 5.17s**, with no exclusions. The acceptance-record test passes; approval records accept the final digest and retain 0.1.2 as an ACCEPT predecessor. Reviewed relevant sources/tests include `src/aew/dashboard/contract.py`, `src/aew/dashboard/server.py`, `tests/helpers/dashboard_contract.py` and the two test modules above.

## Scope

Contract review only. This does not accept frontend rendering, fixture coverage, generated client schemas, live sessions, backend additions or packaged deployment. S1/S2 retain the merged proposal's runtime obligations. The reviewer wrote review records only; implementation, contract and approval records were not edited by the reviewer. Confidence: high. Later contract byte changes require renewed review.

Final C0 ACCEPT at artifact SHA256 `417fa77739a006d65605737794efa6b957c68b6cecd9f6a4d0fd1869272187fb`.
