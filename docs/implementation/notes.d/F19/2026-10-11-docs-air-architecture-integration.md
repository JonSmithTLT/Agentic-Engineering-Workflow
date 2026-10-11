**Architecture integration decisions (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** Slice S18 is temporary unless factored into
the common gateway: F19 must not become the permanent owner of provider mediation, and S18, not built yet, is specified
as a client of F18.15's accounting hook (AIR-24). Evaluator records gain a correlation to the product's ids (AIR-63).
F19 produces qualification evidence for models per role but does not own product eligibility, which is the
execution-profile and model-routing policy's (F46, AIR-70). F9.1's kinds are evaluated in the messaging arms, off in
M4-H.
