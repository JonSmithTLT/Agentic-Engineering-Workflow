**Provider mediation (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md) §6).** The gateway's usage stays authoritative for a provider whose
responses report prompt, completion and total tokens but not cached or reasoning tokens; F25's new semantics value keeps
those unknown, never zero, because the harness stores unreported fields as 0 (AIR-83). The gateway, F18.8 with F28, is
now a deployment prerequisite for providers that require a client certificate (AIR-82), so this convergence lands on the
same mechanism those deployments need first.
