MS5 records an offer in the worker's thread before the supervisor asks OpenCode to steer the run. A successful
offer is followed by a session-message read that confirms admission. Held sessions receive staged inputs. A
relaunch carries current pending messages, earlier unconfirmed offers and unresolved messages selected from the
previous runs, with receipts tied to the new launch prompt. Admitted coordination remains provenance and leaves
the control revision, scope and assignment unchanged. The one-shot admission reconciliation runs on revocation.

The progress digest already shipped in #354. MS5b still owns report finality, turn-end delivery, recorded
`harness send` and the change to enable messaging by default. E248 and operator live qualification remain open.
