**Provider mediation (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md) §6).** Models per role gains a fifth independent runtime fact,
principal accessibility: a model can exist while AEW's credential may not use it (HTTP 403). It is separate from the
eligibility verdict and the operator cannot override it (AIR-78). A 403 is not retried for the same invocation or model,
it updates the accessibility observation, and fallback stays inside the adopted allowed set (AIR-79). Provider
capability flags can establish technical incompatibility, never qualification or authority (AIR-80). AEW or the gateway
queries the provider's model-information endpoint, and the harness's model configuration is only a projection (AIR-84).
The Work and Source cells now name these.
