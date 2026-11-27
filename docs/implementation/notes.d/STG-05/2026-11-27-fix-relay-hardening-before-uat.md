**The provider relay before the UAT, 2026-11-27 (CS-3b).** Built in `fix/relay-hardening-before-uat`, from a
readiness audit of the relay that found its HTTP handling sound:
- **A failed answer's body:** the relay removes a credential from a failed answer's body before it reaches the run.
  On a route whose grant holds a credential, a non-2xx answer is held first, until its end, the record's excerpt
  bound (`relay.EXCERPT_RAW_BYTES`) or `relay.EXCERPT_DRAIN_S` (so a slow one's head goes on up to that much later),
  and the grant's credential values are taken out by the same redaction the record's excerpt uses (`relay._Scrub`).
  An answer whole within the hold that holds none goes on exactly as the upstream sent it; a whole one that holds one
  goes on without it, framed by its new length; any other goes on cleaned as it comes, unencoded and chunked (or
  ended by the close to an HTTP/1.0 client) (`ProviderRelay._failed_answer`). A 2xx answer, and any answer on a route
  that holds no credential, streams as before, untouched.
- **A relay that is gone:** the shim's relay leg answers a fixed `502` with `X-AEW-Refusal: relay_unreachable` when
  its relay takes no connection, as while a run ends, instead of a bare reset. The answer is the relay's own
  (`relay.unreachable_answer`), carried in the leg's spec (`netns.relay_leg`). The egress leg is unchanged.
- **The HTTP path end to end:** `tests/integration/test_relay_http_path.py` sends real HTTP through the shim's relay
  leg, the relay's socket file and a local fake upstream: a streamed answer event by event, a 429 with its
  `Retry-After`, 4xx and 5xx with their bodies, `100 Continue` with a 16 MiB body, a 16 MiB chunked model call, a
  refused HTTP/2 preface, a failed answer's body, and the relay gone.

**What remains**
- **A cut close-delimited answer:** a body with neither length nor chunking that the upstream cuts still ends at the
  harness in a clean close, and so does a failed answer cleaned as it streams to an HTTP/1.0 client. HTTP/1.1 cannot mark it, and the shim's leg to the relay is a socket file, which carries no
  reset. The record says `upstream_broken`; the relay's docstring states the limit. Providers stream chunked, so the
  audit judged it unlikely.
- **The operator's preflight on the UAT host,** not built here:
  - run the live check of the relay's operation and body scopes once against OpenCode 2.2.6
    (`tests/live/test_opencode_live.py::test_every_request_a_real_session_relays_is_in_the_relays_default_operations`,
    with `AEW_LIVE_OPENCODE_MODEL` set to the UAT's provider and model), for a key provider and for the
    client-certificate provider, and record the measurement in `tests/fixtures/opencode/relay-operations-2.2.6.json`;
  - watch how OpenCode backs off on a 429, and whether runs on one model share a rate-limit bucket (SYS-47's first
    live check, E123's note of 2026-11-09): count `upstream_status:429` in the relay journals, with the Lead and two
    workers on one model before scaling up.
