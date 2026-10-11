**Q6a and `interactions[]` (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** This amendment is owed now and is reviewed together
with F41.5's; v0.5 activates only after both exist (AIR-07). It also carries the parent plan's `interactions[]` (F14.1):
the same parent-plan contract, never a second one, with `SERIAL_REQUIRED` compiled to the existing blocking dependency,
`CONDITIONAL` governing only through closed engine-evaluable predicates, and lint at plan acceptance (AIR-29 to
AIR-32).
