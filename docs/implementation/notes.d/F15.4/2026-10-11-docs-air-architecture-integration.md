**Classifications from the architecture integration decisions (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** F15.4 owns the
classification and effective-boundary semantics the operator settings surface (F46) shows for each operator-editable
setting (AIR-67). For models per role: `allowed_models[role]` is legality-affecting (membership changes go through
`adopt`), and `model_preference_order[role]` is operational when it only reorders the adopted set (AIR-71, AIR-72). F45's
`gates.post_integration.base_drift_overlap` is legality-affecting and enters the obligation's basis only when set
(AIR-10, AIR-12).
