**G3-C: the owner consumes.** At the O-01 carrier's admission of a protected member, the owner computes G3's standing
once for the request, never cached and not again after `CONSUMED`. When it fails, or the carrier has no project or the
member no proof, the member is held, `ORIGIN_NOT_ESTABLISHED`, with nothing allocated and consume not called. When it
holds, the owner consumes once with the digest of the set it received: `CONSUMED` is admitted, a refusal is rejected
through the sealed table, and a service that gives no result holds the member (G3-11). An admitted member carries its
operation, with the effect `NOT_OBSERVED` and no evidence ref, since no owner here performs a protected action. A
successor member with no session is also held now.

**Limits.** Consume runs inside the carrier's ledger transaction, the fence against a retry of the key consuming twice.
So a stalled service holds the ledger for up to one read bound per member (8 x 30 s), longer for an answer sent in
pieces, plus the register's lock (10 s), and other submissions get a `503` meanwhile; reads do not wait. A transaction
that fails after consume leaves the member used, which fails closed. The wire has no field for why a member was held, so
the route's log says it.

**Not in this slice, with no row until now.** `aew harness status`'s opening `g3` line, with `label.json`'s session pid and
`start_id` (addendum 7), and the site's line "G3 is not established here", which is blocked-on-you's slice, frozen with
the dashboard work. This note is where they are tracked; E112, whose work they read, is closed.
