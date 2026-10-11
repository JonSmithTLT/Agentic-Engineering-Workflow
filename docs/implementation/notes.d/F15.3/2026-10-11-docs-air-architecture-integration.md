**Reviewer independence refined for advice exchanges (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md), AIR-53).** Reviewer and verifier
context always sees that a consultation occurred, its id and provenance, the bounded question, the refs supplied and the
advisor's disposition and response, but by default not the worker's `proposed_answer` or `uncertainty_reason`, which
are implementer reasoning; an investigation or debug mode may reveal them with provenance when policy permits. Admitted
Lead instructions are not implementer reasoning and do reach those packs (AIR-21, F9.2).
