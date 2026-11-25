**#576's quick-check follow-on q1 (minor) is fixed, branch `fix/map-read-refusal-cause`.** A worker's map read that
its run's bridge does not offer was always refused as `maps_reads_off`, even when the cause was a role card that
narrows `context.read` away (the operation the map reads ride), where turning the switch on would not help. The
refusal now names the switch only when the invocation is offered `context.read`, read from `whoami` (the same
`operations_of`), and otherwise names the role card's restriction (`PERMISSION_DENIED`, reason
`context_read_narrowed`, with the card's id). The next step it gives is unchanged.

**PR A2 (the Lead's typed `map` tool) is not built and waits on the operator's choice.** O2 approved it with an
allocation under the pool cap, but two limits leave no room. The pool's baseline plus its allocations already equal
the operator's cap of 2026-11-15 (42,971 B), and a `map` row measures about 605 to 633 B of tool list before any guide
line. With messaging on, the normal surface already offers 16 tools, TLS-21's retained ceiling, so a new row would
make 17. The routes put to the operator are: raise the cap and amend or except TLS-21's ceiling; fold the map reads
into an existing tool (the consolidation E231 names), which still needs bytes; take bytes from an estimate; or drop
A2, so the Lead keeps the relayed `aew map show` and `aew map search`.
