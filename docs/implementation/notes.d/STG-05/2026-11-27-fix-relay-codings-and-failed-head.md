**The provider relay's codings and a failed answer's head, 2026-11-27 (CS-3b).** Built in
`fix/relay-codings-and-failed-head`, after `fix/relay-hardening-before-uat` (STG-05's note of the same day), with the
operator's approval of 2026-11-27:
- **The relay asks only for codings it can read:** the `Accept-Encoding` it sends upstream keeps only the client's
  codings among `relay.READABLE_CODINGS`, in the client's order and with their weights; a `*` stands, with its weight,
  for each of those the client does not name; and it is `identity` when none is left or the client sent none
  (`relay._accept_encoding`). A 2xx answer still streams as
  the upstream sent it; only the coding the upstream picks can differ.
- **A failed answer's head is cleaned like its body:** its reason phrase and each field value have the grant's
  credential values taken out by the same redaction (`relay._scrub_head`, over `relay._Scrub`), before the head goes
  to the run. Its framing and coding fields (`Content-Length`, `Transfer-Encoding`, `Content-Encoding`) are left as
  they came, so the body is read as the upstream framed it, and a head that holds none goes on byte for byte.
- **Tests:** `test_the_relay_asks_the_upstream_only_for_codings_it_can_read` and
  `test_a_failed_answers_head_reaches_the_sandbox_without_a_held_credential` in `tests/unit/test_provider_relay.py`,
  and their counterparts through the shim in `tests/integration/test_relay_http_path.py`.
