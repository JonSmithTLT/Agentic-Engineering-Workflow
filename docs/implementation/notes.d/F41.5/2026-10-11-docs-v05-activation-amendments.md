**Written and proposed (2026-10-11), awaiting the designer's adoption:** the
[WC §8 / E19-B interface-dependency amendment v0.1](../../../design/wc8-e19b-interface-dependency-amendment-v0.1.md)
(ledger IDA-01 to IDA-28). It extends WC §8 with the non-blocking `interface_dependency` edge (blocking edges unchanged;
an engine-computed digest; `INTERFACE_CONTRACT_DRIFT` at publish), puts the edge in the consumer's E19-B dependency field
group (§2.3), extends E19-B §7.5's `revision_impact_hold` trigger to accepted interface revisions, and defines the
`interface_digest_current` condition a `CONDITIONAL` interaction can use. The decisions-due item now asks for its
adoption, with answers to its open questions I1 to I6 (IDA-22 to IDA-27). Reviewed together with F41.1's amendment.
