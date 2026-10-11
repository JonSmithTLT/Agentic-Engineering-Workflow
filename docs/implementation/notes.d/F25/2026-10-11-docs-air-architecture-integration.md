**Architecture integration decisions (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** Gap 5: the projections get an actual consumer
surface, with the Lead's and F20's presentation (AIR-35). Usage stays one vocabulary under F25, and F18.15 adds a
gateway trust and source value; the gateway's usage event is authoritative and F25 cross-checks it (AIR-24, AIR-60). CI
and check time are process metrics (F42.1), not F25 model usage (AIR-39). The audit's AX-10 (the Lead's usage) is filed
with this row's Lead part and its decisions-due item by the lead developer (AIR-42; a register placement, not a
designer ruling).
