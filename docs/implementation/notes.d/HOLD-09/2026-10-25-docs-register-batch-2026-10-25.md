**An input for this group's matching** (map v1.20 §7, item 3.4), from the designer's rulings of 2026-10-25 on the Lead's
friction log, batch 7 (B7-2, B7-4, B7-6). Nothing in batch 7 is built before V-01 (B7-S), with one exception, in
HOLD-15.

- **The merged result is checked before an integration is admitted** (B7-2, derived from CNI-06.b, with A-07's
  AEV-06):
  - the checks whose result depends on the whole tree, the generated output and the register among them, run on the
    merged result at the current base;
  - evidence names the base and the check definitions it ran with, and a change to those definitions since makes the
    evidence stale for the gate;
  - each merged result gets its own result, which attribution needs;
  - where a host has a merge queue that tests each merged result, AEW may use it, but never depends on one.
- **F9-A1's next revision, as requirements of this group** (B7-4 (1) to (3)). F9-A's live-delivery probe ran on
  2026-10-10, and ADR-0017 records its transport.
  - **Delivery states** are only what the transport can attest: recorded, delivered (admitted to the session), and
    consumed at a step boundary where the harness reports it. "Read" is the model's claim and is never a delivery
    state. ADR-0017's derived facts (recorded, acknowledged, replied-to) are the start.
  - **Supersede:** a message may name the message it replaces, and the inbox shows the current set. A superseded
    message stays recorded, and superseding creates no authority (CNI-04.b, CNI-04.e).
  - **A stable address:** a worker is addressed by its work identity and its run, never by a display name, whether it
    is busy or idle. A lost session is told apart from an unknown message.
- **The publish path's gate** (B7-6, CNI-06): it refuses public text that contains a private finding's identifier, or
  its repro's path.
