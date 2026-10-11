**Raised to a deployment prerequisite (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md) §6).** With F18.8, the gateway's credentialing relay
holds a provider's mutual-TLS client certificate and key, which never enter the sandbox (AIR-81), and it is a deployment
prerequisite for any provider that requires a client certificate, because the pinned harness cannot present one
(AIR-82). The target cell names the new §1 gate beside the internal-alpha one; for other providers Q5's milestone and its
order are unchanged.
