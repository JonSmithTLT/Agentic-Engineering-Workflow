**What F46.3 joins on, and a binding note on its catalog cache (the F46.1 proposal §3.4 and §5, reviewed CLEAR;
designer- and operator-approved).** F46.1's projection (`aew settings show execution`) gives each profile C1's
`identity` and a `connection_id`: `conn-` plus the first 16 hex digits of the SHA-256 of
`canonical_json([project_id, harness, provider])` (`aew.engine.configuration.connection_id`), one connection per
distinct `(harness, provider)` over every profile. A connection's `endpoint` is `NOT_SUPPLIED` and its `catalog` is
UNSUPPORTED (`AWAITS_F46_3`); F46.3 fills them in, may add connections for providers the harness reports under the
same id rule and shape (`profiles: []`), and marks a configured `identity` with no catalog row as an unavailable
reference. F46.1 never queries a provider.

**Binding note (the web developer's, adopted with the proposal).** `connection_id` is a logical project, harness and
provider join key. A catalog's request and cache identity must also distinguish the endpoint or catalog source and the
principal or authorization generation, when those change. A stable `connection_id` alone is not proof that a catalog
observation is unchanged. F46.1 adds no catalog field.
