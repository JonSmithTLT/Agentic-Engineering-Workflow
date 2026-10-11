**Raised to a deployment prerequisite (designer, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md) §6).** The gateway owns a provider's mutual-TLS
transport credential, the client certificate and its key (AIR-81). A harness probe of 2026-10-11 found that the pinned
harness (OpenCode 2.0.18) speaks chat completions but cannot present a client certificate, so this row with F28 is
raised from Q5's hardening priority to a deployment prerequisite for any provider that requires one (AIR-82; the target
cell and a new §1 gate say so). Fields the harness always sends (`stream_options.include_usage`, `store: false`,
`strict: false` on tools) are qualified live; the gateway strips or translates only proven incompatibilities (AIR-85).
