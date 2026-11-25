MS5 records an offer in the worker's thread before the supervisor asks OpenCode to steer the run. A successful
offer is followed by a session-message read that confirms admission. Held sessions receive staged inputs. A
relaunch carries current pending messages, earlier unconfirmed offers and unresolved messages selected from the
previous runs, with receipts tied to the new launch prompt. Admitted coordination remains provenance and leaves
the control revision, scope and assignment unchanged. The supervisor keeps its heartbeat independent of delivery.
On revocation it uses one bounded admission check and continues teardown if the coordination write fails.
Continuation records retain the category and source thread position so C5 can check a failed turn against its log.

The progress digest already shipped in #354. MS5b still owns report finality, turn-end delivery, recorded
`harness send` and the change to enable messaging by default. The operator's live qualification follows MS5b.
