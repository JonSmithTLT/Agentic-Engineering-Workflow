**The provider relay's header values are now validated (RFC 9110 §5.5), 2026-11-25.** A request whose header value
holds a control character other than HTAB is refused 400 `bad_header` before anything connects. Chunk extensions and
trailer fields are held to the same field-value rule (RFC 9112 §7.1.1, §7.1.2; RFC 9110 §5.5), refused `bad_chunk` and
`bad_header`, and a `Content-Length` of other than ASCII digits is refused 400 `bad_framing`. The field-line rule has
one owner, `aew.harness.containment.http1`, which the egress proxy will use too when it forwards plain `http://`
(E92).
