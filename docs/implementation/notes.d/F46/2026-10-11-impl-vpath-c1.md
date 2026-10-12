**The model identity the catalog builds on (built 2026-10-11; [ADR-0010](../../adr/0010-execution-profiles.md),
amendment 2026-10-11).** One rule, owned by the harness adapter (`HarnessAdapter.model_identity`, in
`aew.harness.models`), maps a model id to three identities: the raw catalog id exactly as listed, AEW's provider/model
pair, and the harness reference. A model typed as OpenCode prints it (`provider/model`) is accepted, with or without a
separate `provider`; a prefix naming another provider is refused, naming the field and both ids it may mean. A
provider's own catalog lists bare ids, which `from_catalog` never strips. The model catalog here fills ids through the
same functions, so a browser never prefixes or strips anything. `aew doctor` reports each profile's harness reference
(`model-refs`) and any `provider_env` variable a launch from the current environment would be refused for
(`provider-env`), which a launch now refuses up front instead of dropping silently.
