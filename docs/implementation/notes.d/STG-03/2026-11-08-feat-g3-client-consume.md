**G3-C: the client's consume call, ahead of its two callers.** `aew.g3client.consume` is an owner's one call to
`POST /g3/v1/consume` (G3-08), with the digest of the set the owner received and the member's own proof. It returns the
service's `ConsumeResult`, or none with why when the service gave none (no answer, a `503`, a `403`, a `400`, or an
answer that is not one), so an owner holds under G3-11 and never reads a silent service as a refused proof. It
lands on its own so that the carrier's owner side and the operator endpoint's adapter can each build on it. Nothing
calls it yet: no protected action is admitted until the owner side lands.
