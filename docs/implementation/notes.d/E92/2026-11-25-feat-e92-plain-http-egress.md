**Built (2026-11-25; ADR-0009, amendment of 2026-11-25).** The egress proxy forwards a plain `http://` request,
absolute-form only, under `CONNECT`'s host check on the URL's `host:port`: the policy, one resolve, R-6 on every answer
and again on the connected peer. One request per connection, with `Connection: close` both ways; hop-by-hop and
`Proxy-*` headers left out; the body framed one way only and bounded; chunk lines and trailer fields held to the
field-value rule; time bounds on the body and the response. Anything else is refused before any DNS, each with its own
reason. HTTP/1's rules have one owner, `containment/http1.py`, shared with the relay (#582, which this carries and which
merges first).

**Left:** SYS-02's `reason` and its egress `evidence` line in `systems.yaml` still say the egress refuses plain
`http://`. #578 (E100) edits the lines around them, so they are updated after #578 merges, or when this row closes.
F28's design §7 ("serves `CONNECT` only") is the designer's text and is left as it stands; the ADR amendment records
the change.
