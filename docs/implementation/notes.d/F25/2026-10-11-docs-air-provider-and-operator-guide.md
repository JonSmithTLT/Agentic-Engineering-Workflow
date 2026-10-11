**A new token-semantics value, to build as a slice (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md) §6.6, AIR-83).** Beside the values of
v0.2 §5.3: prompt, completion and total tokens known, cached and reasoning tokens **unknown, never zero** (its name is the
slice's choice). The gateway's usage is authoritative and the harness's a cross-check. The harness stores a usage field
the provider did not report as 0, so a harness-side figure cannot tell "not reported" from zero; the slice must not price
or project such a zero as a measured one. It is a slice of this row: it extends the semantics set
and its conformance fixture, and changes nothing already built.
