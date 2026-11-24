**What the meter can read from the relay's entries (2026-11-24, STG-05's bounds and outcome).** Each relayed request's
entry now carries a `request_id` (one per request: the relay makes one attempt and never retries), the
`policy_sha256` of the execution policy its relay was started from, `client_certificate_sha256` where a client
certificate is used, how its stream `ended`, and an outcome of `forwarded`, `refused` or `unknown`. `unknown` means a
byte of the request may have reached the provider and the exchange did not end whole (a broken connection, or a stream
cut at the relay's time bound): per `RHC-X03` and `R01-08` the meter keeps such a request's encumbrance, never reads it
as not sent. Usage itself is not recorded: that is this row's.
