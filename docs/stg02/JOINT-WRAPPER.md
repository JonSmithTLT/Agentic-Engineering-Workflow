# Joint-mode wrapper

Date: 2026-10-20. Implements setup step 2 of the designer's shared `handoff/JOINT-TEST-BRIEF.md`. This is website test tooling, not an Engine implementation or a new contract.

## Modes and isolation

`serve_recordings.py` defaults to `--mode fixture`, retaining local derived waiting/run fixtures and existing fixture forwarding. Its new explicit `--mode joint` never validates, loads or serves those local bodies. Every `/v1/read/` and `/o01/v0/` route goes to the explicitly supplied loopback upstream port. Static UI assets alone are served locally. `/_test/` probes are not forwarded; the shared brief directs those at the backend itself.

Joint mode forwards the method, encoded path/query, exact request bytes and the selected wire/content negotiation headers. It relays status, raw response bytes and end-to-end headers without JSON parsing, stamp interpretation, version repair, redirection following or automatic retry. Connection/framing headers are handled by the proxy. Missing wire headers remain missing. A transport failure produces a plain-text 502 without adopted wire headers, never a substitute fixture or an owner outcome.

The shared brief deliberately uses a synthetic fixture recipient, no bearer. Authorization and Cookie are neither forwarded nor injected. The only upstream address is `127.0.0.1`, and joint mode requires an explicit upstream port and static build root. It does not start or contact the upstream during startup, static-page serving or asset serving. The backend developer retains control of fresh state and startup.

Transport bounds: 10-second socket deadlines, 64 KiB request bodies, 4 MiB response bodies, no chunked request framing, and a required finite process lifetime (1–3600 seconds). These are test-host limits, not adopted wire limits or new owner semantics. The selected joint request must fit them; an exceeded bound is a wrapper limitation, not a backend result.

## Verification

Run standalone, without importing Engine code:

```text
python -I -B docs/stg02/test_joint_wrapper.py
```

Eight tests use only ephemeral, owned loopback stub servers, not port 4261: all API routes including waiting/run, raw body/query/status/header preservation, all forwarded methods and HEAD framing, no credential forwarding, no header repair or redirect following, static startup with zero upstream requests, unavailable upstream as transport failure, non-API rejection, and default fixture-mode regression. The local waiting helper is poisoned in joint-mode checks so a hidden fixture substitution fails.

Before implementation, the six original tests failed because the server factory/joint interface did not exist. That is missing-interface evidence, not a claim that all proxy semantics were independently exercised on the old host. Initial sandbox temp/socket restrictions are preserved separately. The first unreachable-upstream trial had a two-second client deadline shorter than the wrapper's ten-second deadline; the client bound was corrected to twelve seconds. Final author result: **8 tests PASS**. No dependency, lock, app source or build output changed.

The app assets remain the frozen runtime `af77308aa48cbc73a73791b58b807c0a9ebdbe55`, manifest SHA-256 `d6ec95cf93b42beb4a3902039a104734e3c3d1289f023f0be7fd55659b0608a1`, documented in `CORRECTION-HANDOFF.md`. Wrapper source has its own reviewed commit and clean-checkout tests; app evidence is not relabelled as a new app build.

## Start after independent review

From the website repository root, using the existing Python runtime and the exact frozen assets:

```text
python -I -B docs/stg02/serve_recordings.py --mode joint --port 4252 --upstream-port 4261 --web-root web/artifacts/commit-freeze/run-ef8dde21/source/web/artifacts/offline-gate/dist-stg02 --lifetime 3600
```

For the actual run, launch the reviewed wrapper from its clean detached source snapshot, supplying that same frozen build root as an explicit local argument. Preserve the wrapper source/tree/script hashes and app manifest separately. Serve the static page only to verify readiness before the backend starts; do not make an API readiness request. Browser URL: `http://127.0.0.1:4252/stg02`.

Once the operator has been told the wrapper is listening, the backend developer can start port 4261 from the agreed fresh synthetic state. No backend source/notes inspection or cross-chat contact is needed. Receive only the shared-brief inputs: backend head, synthetic identities, fresh-state identity and the separately generated `command.continue_eligible_work` JSON body. Start the browser with fresh origin-local recovery state. Do not use the built-in old fixture request against the joint backend.

All joint steps and probes remain unrun at this tooling checkpoint. Record actual commands, both heads, fresh state, sanitized traffic and classified mismatches in `JOINT-TEST-NOTES.md`. No remote PR CI or assurance has been observed for this local wrapper change; author checks and independent code review are not CI qualification.
