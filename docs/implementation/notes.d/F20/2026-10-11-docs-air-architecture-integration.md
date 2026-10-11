**Architecture integration decisions (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** The dashboard's `health` projection is to be
renamed project health in the next contract change; run health is reserved for U1 and H1 (AIR-58). F25's projections
get a consumer surface with the Lead's and F20's presentation (gap 5, AIR-35). F20 presents the operator settings
surface (F46), whose first write-capable flow waits for its security design; the dashboard never writes control state
(AIR-65 to AIR-68). The dashboard's attention derivation converges on `ActionProjection` (F43 S1, AIR-17).
