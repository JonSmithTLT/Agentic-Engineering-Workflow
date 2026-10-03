# Future preview registration

Accepted API 0.1.2 remains in `../registry.ts`. A new preview registers a separate
canonical versioned wire artifact and SHA-256, runtime parser map, matching
fixture names/version/digests, and PROVISIONAL disposition. Schema acceptance,
fixture conformance and frontend behavior acceptance are separate facts.

Preview contracts that expose explanations must explicitly represent **no
explanation supplied**. Frontend code may not synthesize explanations from
adjacent fields. Missing, unknown and denied explanation states must remain
expressible; this guidance does not prescribe a future Why wire shape.

Do not extend accepted parsers with speculative fields or weaken strict validation.
The milestone proposing each domain owns its artifact, question ledger and review.
No Journal/context/guarantee contract is registered by W01. Demo-only registration,
fixtures and handlers must stay behind dynamic demo imports. Main-line acceptance
must identify the exact canonical version, digest and reviewed commit before live
adoption, with types, runtime schemas and fixtures updated together.

Scenario configuration in `mock/lab/config.ts` is developer harness configuration,
not an API contract. Route + per-route request ordinals are only authored replay
matching. Extra harmless requests may shift ordinals; update/diagnose scripts,
never impose request ordering on backend semantics or production behavior.
