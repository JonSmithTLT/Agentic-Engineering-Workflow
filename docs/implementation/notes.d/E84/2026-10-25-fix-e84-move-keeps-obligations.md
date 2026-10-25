**Built on this branch (2026-10-25).** A move or a promotion that would lower a unit's inherited obligations is
refused (EW-U05.g): its effective class, a non-waivable gate it inherits, or, for a mutating Ticket, an integration
validated by a verifier. The refusal's code is `OBLIGATIONS_DROPPED` (the code registry, `vertical-uat.md` §8.4), and
its details list what the Lead may do instead. ADR-0007's amendment of 2026-10-25 says why the move refuses rather than
carries the obligations.

**The claim was widened to a promotion.** The designer corrected it on 2026-10-25 (design workspace `3564be3`) to
"a move or a promotion keeps the moved work's inherited obligations, or is refused", with `work promote` a FIX
beside `work move`; this row's Work and Source still name the move only.

**A follow-on, not built:** a promotion could carry the obligations onto the new parent instead of being refused,
since that parent is a new unit whose own policy can hold them. The designer rules this the right path there; it is
to be its own register row.
