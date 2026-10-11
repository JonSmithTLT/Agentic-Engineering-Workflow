**D4's verification half dropped (designer, Q6b, 2026-10-11; [the architecture integration decision record](../../../design/decisions-2026-10-11-architecture-integration.md), AIR-08).** The designer chose not to design a
claim model to save `gates.requires_disposition`'s verification half (`unrequired_verification_results`): MIC-07,
MIC-08 and MIC-16 are superseded, and this row's decisions-due item for that definition is removed. A consequential
verification fact that does not gate goes through the existing observation and finding records and the review half of
`requires_disposition`. Removing the built key, which marks nothing today, is an implementation follow-up of this row.
