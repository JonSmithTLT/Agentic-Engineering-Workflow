**Q5 (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md), AIR-06).** F18.6 and F28 are prioritized as one hardening milestone: first
remove credential exposure, then force all provider egress through AEW-controlled routing; the proxy's usage ledger is
authoritative and harness-reported usage a cross-check; ordinary production qualification requires mediation
completeness. Within the milestone this row is principal separation, not the gateway's owner (AIR-24).
