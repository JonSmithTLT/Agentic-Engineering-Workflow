# STG-02 website implementation notes

This is an isolated fixture slice, not migration of the existing dashboard or qualification of a live deployment.

## Entry and sources

`web/stg02.html` and `web/src/stg02/main.tsx` provide their own entry. In Vite `--mode stg02`, `/stg02` resolves to this entry on dev port 4251. It does not mount the provisional dashboard provider, run its bootstrap reads, alter its parser, or import its demo fixtures. Normal production/demo entry selection stays unchanged. The separate compiled output is `web/dist-stg02/`.

The isolated client consumes only the selected D-01/O-01 route groups. Run/work path parameters are unpadded canonical UTF-8 base64url, not percent-encoded raw identities. Owner-operation path parameters use their own explicit schemas. The index receives no speculative `limit` parameter. Every HTTP request/response checks the selected version, media type and no-store headers; malformed responses and receipt/route binding mismatches are refused before display. A 404 has one nondisclosing treatment.

The copied D-01 and command JSON schemas are byte-identical sealed files, pinned by the generator. `o01-response.json` is a JSON serialization of the sealed O-01 OpenAPI components; it is derived, with its own pin, not an edited wire. The action registry is copied unchanged. Generation adds no dependencies or changes to the lock/generated accepted types.

## CSP and schema assertions

The installed Ajv 6 compiles with `new Function`, which is unsuitable inside the browser under the strict CSP. `generate-stg02.mjs` performs that compilation offline and serializes static validators and their references. Runtime imports only the static functions and the existing format/equality helpers. No unsafe-eval exception is added. The sealed schemas' only observed later-draft assertion is `minContains: 1`; draft-07 `contains` has the same assertion. Other later-draft assertions are rejected by the compatibility step. Assertions beside `$ref` are explicitly enabled; a negative test catches the default Ajv behavior of ignoring them. The independent Python input check uses the original 2020-12 schemas.

The generated validator is large. The isolated build currently emits a chunk-size warning; it has not been hidden or represented as a performance pass. Specialization or more compact generation can be assessed without altering the schema, after correctness. No source proof or authoritativeness follows from structural validation.

## Fixtures and independent boundaries

`serve_recordings.py` derives explicitly unqualified waiting/run fixtures from shape examples. It supplies the synthetic `ticket:one` work binding and an explicit source link to `invocation:demo-1`; the browser never constructs this relationship from prose or IDs. It preserves the original recordings and validates the derivatives against the original D-01 schema before serving. The collection membership is unknown, not fabricated complete. Source fact references are labelled `fixture:`.

Other reads and commands forward to the designer's expressly permitted fixture service over loopback. Its fixture-only C17 effect is not a real HEB implementation or live guarantee. `fixture-continue-request.json` is the separately supplied request from that service's written config; the UI lets the operator review and deliberately select its named work. Continuation state is not an input to command preparation or enablement.

Recorded full/partial/index/error specimens in the browser suite are intercepted recorded-response checks, distinct from the journey's real fixture HTTP requests. Stale is an explicitly derived historical run specimen with unqualified stale source stamps. None is deployment evidence. The four unwitnessed A-23 examples are shape examples only, per the operator's clarification.

## Recovery and lifetime

Before every dispatch, the UI stores a versioned recovery envelope containing the validated exact serialized request and a non-retryable `in_flight` marker in tab-scoped sessionStorage under an origin-local, package-digest key. No credential or operator session is used. Storage refusal prevents dispatch. An in-flight ref prevents duplicate pending sends. A genuine lost response permits an explicit identical-body/key lookup only after that recovery disposition is persisted. No automatic retry or regenerated key exists.

All five adopted `retry=never` Problem codes remain blocked after reload. Other retry directives and their prerequisites are displayed, but this fixture slice cannot establish reauthentication, refreshed entitlement or source recovery, so it offers owner reads rather than asserting that a prerequisite was met. An interrupted dispatch or failed post-response persistence leaves the durable `in_flight` marker blocked after reload. Invalid/legacy recovery records also block new dispatch; they are not silently interpreted as permission to retry. This conservative local recovery policy does not establish owner retention or expiry.

Reload never issues a POST. Validated receipts persist their ordered result mappings alongside the original request. Owner reads check path/envelope identity and redundant nested owner, operation and intent bindings. When a persisted receipt identifies the exact owner/operation pair, its original request-set, intent, recipient and installation must also match before publication. Unrelated operations acquire no inferred request association. The browser cannot independently prove inaccessible owner-native records.

This is one synthetic recipient/installation in one fixture deployment. The tab recovery lifetime is the tab's sessionStorage lifetime; it is not a claim about owner-ledger retention. Multi-recipient/session switch behavior is not qualified and no real authentication/session adoption is claimed. Protected G3 actions have text-only held states, no action controls or dispatch path.

All reads are manual with a 15-second request deadline. Fixture processes use finite lifetimes; headless browser checks use fresh synthetic profiles, service workers blocked and a total deadline. Owned subprocesses are terminated in cleanup. On this host, cross-session loopback failed; starting the fixture services and browser in the same bounded harness succeeded. This is a host/test setup observation, not a backend interoperability result.

## Reproduction outline

1. Extract and hash-check the sealed archive into an ignored artifact folder; run `check_adopted_inputs.py` with a Python containing Draft202012Validator and PyYAML.
2. From `web/`, run `node --experimental-strip-types scripts/generate-stg02.mjs --check`, typecheck, lint and the STG-02 tests.
3. Build with `node node_modules/vite/bin/vite.js build --mode stg02` using pinned Node 22.
4. The designer fixture service and the wrapper must share a reachable loopback network context. The wrapper can serve `--web-root web/dist-stg02` on a chosen free port, forwarding to a separately started synthetic fixture upstream. Use `--lifetime` for every wrapper invocation and a bounded supervisor for the upstream.
5. `browser-stg02.mjs` accepts `CHROMIUM_PATH` and a synthetic-only `STG02_BASE_URL`. Optional `STG02_SPAWN_FIXTURES=1`, explicit `STG02_PYTHON` and `STG02_DESIGNER_DRIVER` start/clean up the owned fixture processes; no backend implementation is read. `STG02_WEB_ROOT` selects the exact frozen build instead of the default working-tree output. External source paths are operator-local arguments, never committed machine-specific paths.

Historical first-checkpoint gates are superseded by the completed corrected-source freeze/review and joint-run records in [CORRECTION-HANDOFF.md](CORRECTION-HANDOFF.md) and [JOINT-TEST-HANDOFF.md](JOINT-TEST-HANDOFF.md). Any later PR head needs its own validation and exact-head review; working-tree author tests and the joint author report are not independent acceptance.
