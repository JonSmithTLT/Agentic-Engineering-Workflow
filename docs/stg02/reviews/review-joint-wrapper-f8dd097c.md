# Independent joint-wrapper corrective review

Head: f8dd097cf9f929c1759820b66b4f169cb32fad11. Previous reviewed head: 041595cff23c0d90d81c5ac2abc89b2a7bb05149. Original implementation base: 50cd41be5b3bf050037e527b781de403c9f88e0b. Date: 2026-10-20.

This is a normal corrective review, not the special nit-only path. Reviewed the complete four-file delta since the FINDINGS verdict, verified both findings, and reassessed the joint host's routing/transport/isolation behavior in context. AGENTS.md, its testing strategy and the shared designer JOINT-TEST-BRIEF.md remain applicable. The prior report is preserved unchanged in the reviewed commit. No backend source, branches/private notes, other chats/people, actual backend port 4261 or joint port 4252 were accessed. Only this new report was written.

## Exact-head CI observation

At 2026-10-20T19:57:34-04:00, local git rev-parse HEAD returned f8dd097cf9f929c1759820b66b4f169cb32fad11. Initial git status --short was empty. This is a local unpublished tooling head. No remote check names, run IDs, completion states or conclusions were observed or queried by this reviewer. Required assurance is NOT OBSERVED; failure attribution remains UNKNOWN. The checks below are independent local executions, not remote CI qualification. Review CLEAR does not establish joint/backend acceptance.

## Findings and nits

None remain. Both prior mandatory findings are closed at this exact head. This pass raises every point it would report; none are held back.

## Prior findings and independent verification

- **JWR-01 closed.** The wrapper validates the upstream Content-Length before publishing source status or headers, rejects invalid/duplicate/conflicting framing, and compares received bytes with declared length for body-bearing responses. The original independent probe from review-joint-wrapper-041595cf.md was rerun unchanged at this head: upstream HTTP200/Content-Length100 with two bytes followed by EOF now produces HTTP502, plain text, no source wire header, and the explicit unknown-command-outcome message. It no longer repairs the failed response into HTTP200/Content-Length2. HEAD remains exempt from body-length comparison; bodyless 204/304 responses are also exempt. The standalone tests independently exercise the truncated, invalid and duplicate fixed-length cases, plus valid raw responses and HEAD.
- **JWR-02 closed.** All host constructors now use LoopbackHTTPServer. On this Windows runtime it disables address reuse and sets SO_EXCLUSIVEADDRUSE before binding. The original independent duplicate-wrapper probe now fails with WinError10048 instead of admitting a second listener. The standalone test also independently proves rejection of an unrelated reuse-enabled ThreadingHTTPServer on the owned occupied port. The CLI constructs/binds before printing its readiness message, so bind failure cannot announce readiness. POSIX behavior preserves ordinary SO_REUSEADDR without enabling SO_REUSEPORT.
- Independently ran sibling mainrepo `.venv/Scripts/python.exe -I -B docs/stg02/test_joint_wrapper.py`, TEMP/TMP set to the writable GitHub workspace, with approved ephemeral loopback access: **11 tests PASS, 2.577 seconds**. No assertion failures occurred in this corrective review. The earlier sandbox WinError10013 and original failing probes remain recorded in the preserved initial report; author fail-before evidence was not substituted for independent execution.
- Independently ran sibling Python `-I -B -m ruff check docs/stg02/serve_recordings.py docs/stg02/test_joint_wrapper.py`: all checks passed. `ruff format --check` reported both files already formatted. `git diff --check` passed for 041595cf..f8dd097c.

## What looks sound

- The complete corrective delta contains only the host, its standalone tests, tooling documentation and the preserved initial review. UI/app assets, contracts, dependency declarations and locks do not change. Formatting and adjacent literal concatenation preserve fixture JSON fields, CSP and transport-error text. The fixture-only urllib annotation accurately describes its fixed HTTP loopback host and numeric upstream port; it does not change execution.
- Joint mode still bypasses local fixture validation/answers for every forwarded API prefix. It preserves method, encoded path/query, raw request and response bytes, source status and selected end-to-end headers. It does not parse JSON, interpret stamps, repair wire versions, retry commands or follow redirects. Authorization/Cookie remain excluded.
- All eleven tests use owned ephemeral stub ports. Independent execution rechecks original API/static/no-startup-probe, no-credential, HEAD, redirect, missing-header, unavailable-upstream, non-API rejection and default fixture waiting behavior alongside the corrections. Startup/static readiness still requires no upstream request; no actual backend was needed for this review.
- Documentation accurately preserves the initial findings, separates tool fixes from backend semantics, and still requires fresh independent review before launch. It keeps frozen UI provenance separate from wrapper source and explicitly leaves all joint journey/probes unrun. The preserved review's prior failed evidence and exact-head CI limitation remain intact.

## Coverage and limits

Framing review covers every bounded upstream response-read path in this host: one joint `response.read` site now validates fixed-length completion before publication; HTTP parser exceptions and oversized replies also enter the same 502 path. The reproducible early-EOF probe from the prior report and the new malformed-length tests establish the repaired class at this revision. This is not exhaustive HTTP parser fuzzing; malformed chunked and every possible framing combination were not independently enumerated.

Listener review enumerated the host server constructor and socket-option setup; the corrected constructor is shared by fixture and joint modes. Both competing-listener controls ran on Windows/Python3.13.1. No POSIX runtime or arbitrary unrelated platform/socket configuration was exercised. The original ephemeral reproduction remains repeatable from the prior report.

No Docker build, UI freeze, browser journey, full fixture/browser regression, dependency installation, source snapshot duplication or real backend interoperability test was performed. Author clean-source tests running separately are not claimed as this reviewer's evidence. The adopted sealed v0.5.4 boundary remains unchanged. Actual joint acceptance still requires the shared brief's steps/probes, both tested heads and recorded traffic.

Review: CLEAR at f8dd097cf9f929c1759820b66b4f169cb32fad11
