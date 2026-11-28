**Built (2026-11-25; ADR-0009, amendment of 2026-11-25).** The egress proxy forwards a plain `http://` request,
absolute-form only, under `CONNECT`'s host check on the URL's `host:port`: the policy, one resolve, R-6 on every answer
and again on the connected peer. One request per connection, with `Connection: close` both ways; hop-by-hop and
`Proxy-*` headers left out; the body framed one way only and bounded; chunk lines and trailer fields held to the
field-value rule; time bounds on the body and the response. Anything else is refused before any DNS, each with its own
reason. HTTP/1's rules have one owner, `containment/http1.py`, shared with the relay (#582).

**Left:** E92's slice stays on SYS-02's `remaining` until this row closes; its `reason` and egress `evidence` in
`systems.yaml` now say it is built. For the designer: F28's design §7 ("serves `CONNECT` only") and the requirements
ledger's NET-24 ("the egress proxy (CONNECT only)") still describe the egress proxy as before E92; both are design text
and are left as they stand, and the ADR amendment records the change (review of #584, m6).
