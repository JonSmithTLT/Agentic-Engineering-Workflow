**E87 built the floor and gate part of plan v8 §3.12's carry (2026-11-27).** A promotion writes `carried_obligations`
on the unit it creates (the floor, its rationale and the mandatory gates of every ancestor it leaves behind), and one
accessor, `hierarchy.ancestor_obligations`, is the walk every reader of an inherited floor or mandatory gate uses
(ADR-0007's amendment of 2026-11-27; invariant 64). The entry shape differs from §3.12's: `{from, via, decision,
min_descendant_class, mandatory_gates, rationale}`, and the carried entries bind the carrier's descendants only.

**Left to F4, unchanged:** carrying the dependency edges, declared-scope envelopes, guardrails and impact holds; the
Story or Epic move carry (and with it folding a unit's own entries into the unit itself); §3.12a's full `inherited`
accessor with edges and scope, its static matcher and allow-list; TR-14, `child_promoted_out` and the enabled or
dormant split. The registry's `carried_obligations` row (written "from S2b.2") is untouched: E87 writes it, and its
classification stands.
