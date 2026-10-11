**Architecture integration decisions (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md)).** The audit's AX-16 (run health into wait and
the projections) is filed on this row by the lead developer (AIR-42; a register placement, not a designer ruling). Run health is reserved for U1 and H1; the dashboard's `health` is renamed
project health (AIR-58). U1's edge-triggered transitions become process events for F42.1.
