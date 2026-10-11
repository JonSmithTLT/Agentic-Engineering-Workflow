**Architecture integration decisions (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** Redaction and work-safe diagnostics are an
F37 requirement from the beginning, not a sanitization pass after a telemetry corpus exists: at least normal logs, check
logs, evidence, coordination bodies, absolute paths, the supervisor's log, the per-run event log, and size and retention
bounds (AIR-37). F37 establishes one canonical redaction-pattern source and an explicit redaction policy, while each
surface keeps its own allowlist and serialization responsibilities (AIR-59). Telemetry stores are linked through
correlation ids, not consolidated, and F37 owns that correlation and redaction boundary (AIR-57). F42.1's persistence and
F42.2 wait for the boundary.
