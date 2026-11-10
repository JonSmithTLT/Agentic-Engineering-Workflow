MS3 adds switch-registered `message_send` to the typed catalog and runner, never the off catalog. MCP snapshots the
broker's presentation hint at startup; the broker validates against its independent adopted-switch snapshot, and the
engine still checks adopted policy and authority under its lock. Messaging on selects description-only compact rows;
off remains byte-identical. Catalog conformance covers all four switch/presentation configurations.
