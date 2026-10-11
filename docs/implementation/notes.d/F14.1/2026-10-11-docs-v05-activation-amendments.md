**Written into F41.1's proposed amendment (2026-10-11), awaiting the designer's adoption:** the
[WC/F14 parent-planning amendment v0.1](../../../design/wc-f14-parent-planning-amendment-v0.1.md) §6 to §8 carries
`interactions[]` with the acceptance's exact shape, the three verdicts, closed `{kind, refs}` conditions
(`interface_digest_current`, defined in the
[interface-dependency amendment](../../../design/wc8-e19b-interface-dependency-amendment-v0.1.md) §7;
`overlap_set_empty`; `dependency_state`), the deterministic lint at parent-plan acceptance and the composition rule
(PPA-13 to PPA-20). Open questions on this row: the direction of `SERIAL_REQUIRED` (P1), how it follows plan revisions
(P2), a condition failing mid-flight (P3), scope on decomposition entries (P6) and the closed condition set (P7).
