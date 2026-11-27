# Scoped bindings for authoritative control updates

**Status:** Adopted 2026-11-25 by the operator. E329 applies the 2026-11-10 design ruling. The operator's cutover decision was “Remove it outright.” The old project-wide input is removed at the cutover.

## 1. Workflow Contract §5, crash-safe control authority

Replace the crash-safe control-authority rule with this rule. Authoritative updates are atomic and require the current Lead authority generation or the operation's equivalent authority guard. An operation that relies on a value the caller read binds that item's prior value. An operation that records a judgment binds the particular content digest or other stable identifier the decision rests on. An operation that can determine what is safe from its own locked inputs does so at commit. An unrelated commit leaves such an operation eligible.

An explicit Lead handoff advances authority and prevents the superseded Lead from overwriting accepted state. An interrupted write recovers to the previous valid state or to the complete new state. Ticket workspaces contain contextual copies of control artifacts and cannot become independent control authorities.

## 2. Workflow Contract §6, authority table

The controlling inputs for the authoritative control-state mutation row are the current authority generation or equivalent authority guard, and the item's prior value or the content digest the decision rests on when its operation requires it. The transaction checks its own admission constraints under the control lock.

## 3. Knowledge Contract §12.3, control state

Authoritative control updates are atomic and stale-writer-resistant. A mutation checks the current authority of its actor and the prior item value or approval subject its operation declares. Admission and persistence use the same control lock. A handoff invalidates the superseded writer. Crash recovery exposes the previous valid state or the whole committed state, and workspace copies are contextual only.

## 4. Knowledge Contract §26, crash-safe control update and superseded Lead

Interrupt persistence during a transition and require the previous valid state or the whole new state after recovery. Hand authority from Lead A to Lead B and require that Lead A's later authoritative update is refused. Lead B can act without a project-wide revision argument. Change a decision's bound item or approval subject after Lead B reads it and require that the attempted decision commits nothing. In-flight work remains reconcilable.

## 5. Applying the amendment

- An operation's declared binding is authoritative. `CHANGED_SINCE_READ` asks the caller to read the subject and decide again. The real commit revision still orders durable transitions, follows log cursors and identifies recorded facts. Project-map compare-and-set uses its own map revision.
- A-44 BOY’s action applicability is determined by the referenced item and policy in force. A-33’s G3 command approval stays bound to its command-set key. A change elsewhere in control state does not consume that approval.
- KSI-02 and KSI-03 require the appropriate Lead or service credential and the operation’s own subject guard in the transaction. A service credential remains limited to its registered family. Issuing, rotating and revoking service credentials remains Lead authority.
- `aew migrate` upgrades legacy open stage intents under the lock. A known old journal may continue if its observed input and remaining plan can be proved. The Lead must deliberately abandon an unprovable intent and decide anew from the current projection. Prior steps remain recorded. Closed historical records retain their original bytes.
