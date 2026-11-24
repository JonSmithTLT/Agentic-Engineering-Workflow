**The provider relay's bounds and outcome (2026-11-24): the relay bounds request size, concurrency and stream time,
and records an honest outcome.** Each bound is an implementation bound stated in `relay.py`, set by the host-side code
that starts the relay, never by a request or the sandbox:
- **Request body:** `relay.MAX_BODY` (64 MiB). A `Content-Length` over it is refused 413, `request_too_large`, before
  the credential is resolved or anything is connected; a chunked body is counted as it comes and refused at the chunk
  that passes it, whose size line is not sent, so the upstream never gets the request whole.
- **Concurrency:** `relay.MAX_ACTIVE` (32) requests in progress per relay. The next is refused 503, `relay_busy`,
  before its head is read, and nothing is connected.
- **Stream time:** `relay.STREAM_TIMEOUT` (an hour), from the request's end to the response's end, its head included.
  A response with no head by then is answered 504, `stream_timeout`; one cut mid-body ends the client's connection.

**Outcome.** The relay never retries. A request any byte of which may have gone upstream, whose connection then
broke, is `upstream_outcome_unknown` (502 when no head had come; entry outcome `unknown`), never
`upstream_unreachable`, which now says the request was not sent. A stream cut by the time bound is outcome `unknown`
too, as the provider may have done the call. A body refused as it arrived (too large, stalled, malformed) stays
`refused`: the upstream never got it whole. Each entry also records `ended` (`complete`, `client_gone`,
`upstream_broken`, `stream_timeout`, `relay_closed`), a per-request `request_id`, the `policy_sha256` of the execution
policy the relay was started from, and, with a client certificate, `client_certificate_sha256` (its leaf's digest as
read at the relay's start; never key material). `aew status` counts an unknown outcome as unknown, never as relay
refused, and `aew credentials` lists it among recent failures.

The live lane (`tests/live/test_opencode_live.py`) now checks that a real session at the pinned OpenCode relays only
operations of `relay.DEFAULT_OPERATIONS` and none is refused for scope: the confirmation the operation scope's note
named as this pull request's.

Known limits, each with its owner: no rate, allowance or reservation (E97, after STG-14); the bounds are not policy
settings (a provider that needs another value is a change here); a relay's bound is its own, not the run's or the
host's.
