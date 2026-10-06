# PR 89 live-runner correction evidence

Web-owned correction verification, 2026-10-06. Independent re-review and packaged-server F20.6 acceptance remain pending. This addresses the two findings against `1051ea8570b4faa80646bba298dd55a8e492beb0`; it does not rewrite the independent review.

Runtime commit: `4b38aad6940748d20937236cb1d3dc06be5f5396`. Repository tree: `4f1526a1e27060651718059dc57f1521207c5bb5`. The build and browser checks used a clean detached checkout of this exact commit. Application source, accepted and preview contracts, generated types and the dependency lock remain unchanged. F20.5 packaging stays pinned to `4f0a710fa4831eefda248dd43cc2e144d1010189`.

## Corrections

- P2: context-level page registration attaches the same script, console and API validation observers to every page, including copied Work links. Reopened checks wait for CURRENT, network quiescence and pending response validation before recording success.
- P3: output validation refuses directories and other non-files with a fixed diagnostic. Both success and failure report writes are independently guarded; persistence failure exits nonzero without filesystem paths, stacks or exception text.

## Verification

The pinned offline Node 22.22.2/npm 10.9.7 gate passed: four input/report boundary tests, artifact and documentation checks, typecheck, lint, 167 frontend tests, production/demo builds and production exclusion. The browser regression passed all seven cases: authenticated desktop/phone; authentication bypass; malformed bootstrap; copied-page-only script failure; copied-page-only malformed projection; directory output; and a report-write failure introduced after input validation. Negative probes assert their intended failure stages and prevent copied-link success from being recorded. Unit tests also cover EACCES, ENOSPC and EISDIR without exposing exception details.

Browser tests used pinned Chromium 1217 with service workers blocked, locked dependencies mounted read-only and a network-isolated container. The owned HTTP adapter is test-only; no Engine server or real session was exercised. Existing W01–W06 browser CI remains configured; the local correction run targets this runner's seven controls. No screenshots or private cookie values were retained.

Source cleanliness and both complete build manifests were verified again after browser checks. Aggregate production manifest: `486c3a2c531c0c46fd5f850fc771598321ce47154a777c67ba21775110f7f89a`; demo: `19030453fa2102481cd834472e61b4d0462ee0588b76bddb9275f1859afbe75a`. Both equal the earlier frozen outputs.

## Reproduction and retained evidence

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/freeze-committed-build.sh 4b38aad6940748d20937236cb1d3dc06be5f5396
```

Copy tracked `web/` and `docs/` from that detached checkout into an ephemeral browser container, copy its frozen production `dist`, and mount the locked dependencies read-only under a `node_modules` path. Run:

```bash
node --test scripts/live-inputs.test.mjs
node --experimental-strip-types scripts/verify-live-runner.mjs
```

Retained: [provenance](f20-live-runner-pr89-correction-2026-10-06/provenance.json), [offline gate](f20-live-runner-pr89-correction-2026-10-06/offline-gate.log), [browser controls](f20-live-runner-pr89-correction-2026-10-06/browser-live-regression.log), [production manifest](f20-live-runner-pr89-correction-2026-10-06/dist.SHA256SUMS), [demo manifest](f20-live-runner-pr89-correction-2026-10-06/dist-demo.SHA256SUMS). Runtime identities and file hashes are recorded in provenance. The disposable browser image adds OS libraries without altering the pinned builder.

## Publication secret scan

Gitleaks 8.30.1 scanned the nine-commit publication history through `dda26b1`. Its sole raw finding was line 48 of the retained offline log, verified in full as the public accepted API 0.1.2 SHA-256. The repository exception records only this exact commit/path/rule/line fingerprint and rationale; no broad exclusion was added. The final history is rescanned before pushing. No credential findings were identified.

## Integration posture

The runner is published through PR #89 on `feat/f20-authenticated-browser`. F20.4 (#87) is merged; F20.5 (#90) and F20.6 (#97) remain separate integration work. Server-half acceptance does not complete the browser gate. Main-line operators must still run the [authenticated live interface](../how-to/authenticated-live-browser.md) against the packaged server, recording server/build/tooling identities and their separate security checks. The reported `integrated` semantic value remains a contract-review question; this correction does not silently accept it.
