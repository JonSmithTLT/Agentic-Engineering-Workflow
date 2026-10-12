**Slice F1b: the contract 0.1.4 change note** ([`dashboard-configuration-read-v0.1.md`](../../../design/proposals/dashboard-configuration-read-v0.1.md),
proposed). Its Appendix A adds `/configuration` and `/configuration/execution` (pending until F1c serves them), the
`configuration` capability key and the projection's shapes, merged into the accepted 0.1.3, which is vendored as
`tests/fixtures/dashboard/contract-0.1.3.yaml`. There is no engine-side schema for the projection, so the appendix is
pinned by tests: the projection's real output over F1a's corpus validates against it, every property it defines is
emitted, and every open enum and bound equals its engine owner (`tests/unit/test_dashboard_config_note.py`,
`tests/integration/test_dashboard_config_note_shapes.py`). The items the earlier note on this row listed for F1b
(`too_long`, `UNPROCESSABLE`, `Capability.reasons` complete) are in the note's §5 and §7, with the other differences
from the proposal's Appendix A. Next: W2, the web developer's adoption, then F1c.
