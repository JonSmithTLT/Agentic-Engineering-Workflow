# Demo screen loading checkpoint

This is a frontend efficiency correction under existing contracts. It changes demo UI loading only; it does not adopt backend routes, change fixture semantics, or refresh the agreed packaged frontend.

## Measured decision

The frozen baseline `1c96281f45a43a696b7635ea444a2949bdbbdfc1` loaded 28 scripts on Overview, Work, Journal and the associated packet. Overview loaded seven unrelated investigation UI modules. A first lazy-loading trial at `e155ebb2c658672a3d03bbb0fc257ebf23663729` reduced requests, but native direct Journal/packet medians increased from 359.2/437.2 ms to 881.4/881.4 ms. That trial was rejected as-is; its samples and failed intermediate test/probe logs were preserved.

Runtime correction `a4a8de97070a29dea66f1c9f6e53ca5a1fd0a02a` loads only the initially requested preview screen before rendering. Other screens and the Playground remain deferred. Initialization and project bootstrap precede reads. Later loading/failure feedback stays inside the requested screen, preserving shell controls and URL ownership.

Three fresh-browser trials per route and CPU profile used the HTTP demo, blocked service workers, disabled cache, viewport 1092×1000 and the same pinned Chromium. Readiness means the route-specific useful heading, followed by a fixed observation window; it does not establish that every read settled. All 24 baseline and 24 corrected trials completed without page errors or failed trials.

| Route | Baseline native ms min / median / max | Corrected native ms min / median / max | Baseline emulated 4× CPU ms min / median / max | Corrected emulated 4× CPU ms min / median / max |
|---|---|---|---|---|
| Overview | 230.5 / 231.3 / 257.8 | 105.7 / 107.2 / 109.5 | 828.8 / 854.3 / 1304.2 | 344.5 / 345.8 / 350.4 |
| Work | 282.4 / 338.2 / 372.5 | 139.3 / 164.3 / 167.0 | 1493.2 / 1580.6 / 1645.6 | 433.9 / 556.3 / 563.7 |
| Journal | 333.0 / 359.2 / 379.0 | 165.9 / 167.8 / 171.5 | 1148.3 / 1336.2 / 1397.3 | 508.0 / 527.0 / 562.6 |
| Packet | 431.7 / 437.2 / 442.4 | 163.0 / 165.6 / 167.8 | 1439.0 / 1584.0 / 1815.7 | 507.2 / 518.0 / 647.9 |

Overview/Work loaded 9 scripts and 1,622,315 decoded bytes from resource entries with script initiator type; Journal/packet loaded 20 and 1,688,887 bytes on the same basis. Baseline was 28 and 1,815,691 bytes throughout. These are local demo observations, not compressed remote transfer estimates or a live-server timing SLA. Three trials are exploratory; CPU emulation is not a physical device. Later first navigation still incurs chunk loading, with visible feedback. Fixture initialization still accounts for substantial bytes and has not been optimized in this checkpoint.

## Verification and evidence identity

The committed runtime was built in a clean detached checkout by pinned Node 22 builder `sha256:14e051132580dc72266926a9c91023e1be7f71211c0086dd5e5a4d9252360b8b`. Offline gate: 173 tests, typecheck, lint, artifacts, both builds and production exclusion passed. Freeze `web/artifacts/commit-freeze/run-PJlqQd9O` records source tree `1c7a44e8bec6d57afc99a8a458d713568a50a1bf` and full inventories. Production inventory digest remains byte-identical to baseline: `0a0925268c7992a42e9a3fbb0351c52343c8edbeeff824aba5a141298f72dc1a`. Corrected demo inventory digest: `e860b1ddb16e05aeeda577aca0e4af3b0761b0dbf7dcf49754d742232a00f6e9`.

Compiled checks cover desktop/phone demand loading, an intentionally delayed chunk with usable shell controls, packet deep links, and an aborted chunk followed by reload of the same selection/tab. The first probe incorrectly waited for a Contents-only item heading on Receipts; that failed probe is retained and corrected to the actual packet heading. No runtime defect was established by that probe failure. Unit tests cover demand, prop updates, contained failure and loader reuse. The HTTP browser gate also checks that Overview and Requests disclosure load no unrelated UI, and that explicit Contract disclosure loads the Playground.

Full before/after samples, commands, intermediate failures, reviews and screenshot outputs are retained in the local review carrier `AEW-reviews/frontend-workstream-2026-10-07`. Local ignored artifacts are supporting evidence; their absence must not be described as an available rebuild bundle. Independent exact-head review and green assurance remain merge gates. This document records measured implementation evidence, not independent product acceptance. No backend requirement or domain semantic change is introduced.
