**MS3 built:** the adopted `coordination.messaging: enabled` switch offers `message_send` on both typed profiles,
with required control-revision CAS, bounded text/refs, sender-scoped idempotency, a broker snapshot and description-only
compact catalog. Recording creates no invocation, credential, run, stage intent or control commit. The result honestly
says delivery is not built yet; `turn-end` is refused until MS5b. Off catalogs, policy/init bytes and Lead environment
remain unchanged. Tests: `test_message_send.py`, `test_message_catalog.py`, the four-configuration catalog tests.

**Operator decision (2026-11-10):** withdraw “switched on after the consult (E158)”. Messaging turns on by default in
the first usable fourth PR (MS5b), with the absent-key-only operator switch offer for old projects. E131 and E175 are
placed. Remaining order: MS4+MS6 (reply/attention), MS5 (live delivery), MS5b (finality, both timings, recorded harness
send and default-on). MS7's real-provider check remains owed, not a default gate. A failed required Linux qualification
does hold the usable release. No current-version binary/provider qualification is claimed by MS3.

**PR 2 follow-ons from the amendment's CLEAR:** use `util.atomic_write` for local told-message IDs, with a stable
separate `.aew/local/lead/told-messages.lock` (and FileLock's `.queue`) to serialize broker unions across JSON rename;
recheck generation under that lock. Name exact settled files, normal temp cleanup and crash cases in ADR-0009/tests;
no relayed store/seen-log/wake writes. The budget's 936 bytes describe explain's **compact entry**, not its standard
entry. The worker_message guide owner is `src/aew/harness/contract.py`.

**Surface-map limit:** MS3 does not implement the whole `harness send` timing surface or interrupt a turn. Those shell
commands stay reachable and their uncovered uses remain explicit; a proposed typed home is not proof of either effect.

**MS3 text limit:** messaging-on MCP tools/list names message_send, but the import-time Lead system summary and the
Ticket-path guide do not name it yet. Snapshot-aware system/guide derivation and the two-configuration naming test
belong to the reply/attention slice. Guide stages keep standard descriptions; only MCP's on-catalog uses compact text.
