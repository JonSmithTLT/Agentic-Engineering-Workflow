**Body-level operation scope for the provider relay (2026-11-24): the relay holds a request body to the provider's
allowed operations, as it holds the path.** For a model call (`relay.DEFAULT_OPERATIONS`' `model`), the relay reads
the body whole before anything is connected and:
- **refuses a field outside the policy:** a body that uses one of `relay.BODY_FIELDS` (fields that name an object
  stored with the provider, or a server of its own), or declares a tool other than a function the client runs
  (`tools.<type>`; every key an upstream might read as a tool's type counts), is refused 403,
  `body_field_not_permitted`, naming each field in the answer and in the record's `body_fields`, recorded `refused`,
  with nothing connected. A key is matched as an upstream might read it: without
  its case, `_` or `-`. A tool call's own arguments and a function's parameters are never read for one. A model call
  is recognized as one whatever `relay_operations` lists, and an entry there naming one, in any letter case, or whose
  path ends in `/`, refuses the start;
- **opts a field in only from the adopted policy:** `containment.network.relay_body_fields.<provider>` (each entry
  one of `relay.BODY_FIELDS` or `tools.<type>`), read on the host at the relay's start, as `relay_operations` is; per
  provider, for its API-key and stored-login relays alike. An entry the relay does not know refuses the start
  (`bad_relay_body_field`). No request, header, query or body opts itself in;
- **refuses a body it cannot read as one JSON object:** 400, `body_unreadable`, nothing connected: not UTF-8, a
  byte-order mark, a key given twice, NaN or Infinity, nesting deeper than `relay.MAX_NESTING` (128, checked before
  the parser, whose own limit differs between interpreters), anything but one object, or a `Content-Encoding`. An
  empty body has no field, and goes as it came;
- **sends it framed by its length:** the body as read, with `Content-Length`; a chunked model call is not passed on
  chunked. Any other operation's body (a policy-listed one's) is streamed as before.

**Memory.** Reading a body whole could cost `MAX_BODY` times `MAX_ACTIVE` (64 MiB x 32 = 2 GiB) per relay, and parsing
it many times its size for many small values (#551's review, m3). Only model calls are read whole, and a relay holds
at most `relay.MAX_HELD` (256 MiB) for them at once: each body from its first byte until it has gone upstream (by its
`Content-Length` before it is read and before a `100 Continue`, a chunked body chunk by chunk), and, while it is
checked, an upper estimate of its parse (`relay._scan`: its text and its strings at the width Python stores
them, and `relay.PARSE_VALUE_BYTES` for each value, measured with tracemalloc). One that would pass the bound beside
the others is refused 503, `relay_busy`, and one that would pass it alone 413, `request_too_large`, with nothing
connected. One body at `MAX_BODY` whose bulk is its strings fits.

**Client reset (#542's quick check, m6).** A client that resets its connection before its request is whole, in its
head or its body, is recorded `refused` (`incomplete`) as a close is, never `unknown`.

**Source of the fields.** No provider's request surface is pinned in the repository, so `relay.BODY_FIELDS` and where
each route's body is read for them are an implementation choice stated in `relay.py`, from each provider's request
reference. Tools take the converse, allow-list rule: only a function the client runs passes. OpenCode's real calls
are not refused: each call of `tests/fixtures/opencode/relay-operations-2.2.6.json`, with its route's ordinary body,
is forwarded (`test_every_model_call_opencode_relays_passes_the_body_scope_with_its_ordinary_body`); those bodies are
written in the test, not recorded at the pinned version, and the live lane's relay check now also asserts that no
request is refused for its body, the confirmation at the pinned version.
