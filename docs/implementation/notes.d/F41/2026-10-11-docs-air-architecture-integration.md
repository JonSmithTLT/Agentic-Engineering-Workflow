**Activation now also waits on F45 and F43 (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** AX-01 is a precondition of activation:
v0.5 §9's claim that integration validation covers undeclared relationships holds only with F45, and an activated
project must have `base_drift_overlap` adopted and on, which the activation gate verifies (AIR-09, AIR-12). The attention
spine (F43) comes first as mainline work F41 depends on (AIR-16). Q6a: the two activation amendments (F41.1, F41.5) are
written now, reviewed together, and v0.5 activates only after both exist (AIR-07). The order: F44, F43 S1 to S3, F45
after E6a, then activation (AIR-75).
