# F20 authenticated live runner verification

Web-owned verification, 2026-10-05. **Packaged-server F20.6 acceptance and independent review remain pending.** No Engine server was used for the browser regression recorded here.

The tooling checkpoint is `cf7a3da235c7334ae974a5840298f9f8276d24f9`, repository tree `aebcf7f846c39467db7fef26d2829380abbdaa7d`. A clean shared clone was detached at that exact commit before building. The approved F20.5 packaged frontend remains `4f0a710fa4831eefda248dd43cc2e144d1010189`; this tooling does not advance that agreement or change accepted/preview schemas, generated types, application source or the dependency lock.

## Results

- Pinned Node 22.22.2/npm 10.9.7 offline gate: PASS, including generated artifacts, accepted/preview digest checks, documentation, typecheck, lint, 167 component/unit tests, both builds and production exclusion.
- Private input/request boundary: PASS, three regression tests covering credential-free target validation, origin-bound/private/bounded cookie files, symlink/hardlink protection, rejected extra state and production-only read traffic.
- Compiled browser regression from the clean checkpoint's frozen production build: PASS, desktop and phone navigation, supplied first-page details, Back, Work copy/reopen, phone heading focus below the sticky header, themes, overflow, session-refusal UI and blocked service workers.
- Negative controls: PASS. Authentication bypass fails at `unauthenticated-api-refusal`; malformed capabilities fail at `desktop-authenticated-bootstrap`. Logs and reports contain no test credential. These assertions cannot pass merely because Chromium failed to launch.
- Engine documentation links: 167 tests passed. Premium static report: zero findings. This changes test infrastructure, not product UI ownership or design tokens.
- Clean source and complete production/demo file manifests remained unchanged after browser verification. Their aggregate hashes equal the earlier frozen outputs: production `486c3a2c531c0c46fd5f850fc771598321ce47154a777c67ba21775110f7f89a`; demo `19030453fa2102481cd834472e61b4d0462ee0588b76bddb9275f1859afbe75a`.

## Reproduction and retained evidence

The build command was the committed-source freeze with the pinned builder:

```bash
SPT_FRONTEND_IMAGE=sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407 \
bash web/scripts/freeze-committed-build.sh cf7a3da235c7334ae974a5840298f9f8276d24f9
```

Browser verification copied tracked `web/` and `docs/` from that detached checkout plus its frozen production `dist/` into an ephemeral container. Locked dependencies were mounted read-only under a correctly named `node_modules` directory. Node 22 ran:

```bash
node --test scripts/live-inputs.test.mjs
node --experimental-strip-types scripts/verify-live-runner.mjs
```

The browser container used `--network none`, the explicit Chromium 1217 path, and a disposable test-only authenticated fixture adapter. Browser OS libraries were staged in a derivative image; the pinned offline builder was not modified. Runtime image, browser executable digest and evidence hashes are in [provenance](f20-live-runner-2026-10-05/provenance.json). Retained outputs: [offline gate](f20-live-runner-2026-10-05/offline-gate.log), [browser regression](f20-live-runner-2026-10-05/browser-live-regression.log), [production manifest](f20-live-runner-2026-10-05/dist.SHA256SUMS), [demo manifest](f20-live-runner-2026-10-05/dist-demo.SHA256SUMS).

## Main-line handoff

Use the [live runner command and private cookie-file interface](../how-to/authenticated-live-browser.md) from a separate tooling checkout against the actual packaged server. Record server/build/tooling commits, actual `BUILD.json`, asset hashes and platform results. Complete security negative controls, expiry/replacement, conditional requests, validator/scope isolation and authorized hostile-content tasks separately. Empty supplied collections leave detail coverage unexercised, explicitly recorded by the runner. Fixture regression PASS is not live acceptance. CI is configured to repeat the runner regression alongside the existing browser suites; its PR result is separate from this local evidence.

## Publication secret scan

Gitleaks 8.30.1 scanned the branch history from `ab990c781030f90655ceb205cde3e1ca2c7f460b` through `26c822b` before publication: six commits, no leaks after the repository's exact history-fingerprint exception. The one raw finding was `generic-api-key` at line 42 of the retained `offline-gate.log` in commit `f5a21be`; the entire line was verified as the public accepted API 0.1.2 SHA-256 emitted by the contract check. The exception records this precise commit/path/rule/line and rationale in `.gitleaksignore`; no broad rule or path exclusion was introduced.

A separate directory scan of the exact final changed-file contents, with inline allow comments disabled, reported only that same public-digest line. It was checked against the canonical artifact and C0 pin. There were no credential findings. Reports were redacted; machine-specific scan paths are not published here. The Linux scanner archive was verified against the official release checksum before execution. The branch-history scan is repeated on the final documentation commit before pushing.
