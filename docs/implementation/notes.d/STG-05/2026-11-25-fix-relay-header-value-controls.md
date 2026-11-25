**The provider relay's header values are now validated (RFC 9110 §5.5), 2026-11-25.** A request whose header value
holds a control character other than HTAB is refused 400 `bad_header` before anything connects. The field-line rule
has one owner, `aew.harness.containment.http1`, which the egress proxy will use too when it forwards plain `http://`
(E92).
