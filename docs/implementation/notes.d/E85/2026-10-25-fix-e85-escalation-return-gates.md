**Built on this branch (2026-10-25).** A return from escalation meets the gates of the phase it enters, and a
reconcile after an interruption meets the guard of the Lead's direct edge from the interrupted phase, where the table
has one (EW-U06.f). This is option C of the R1 plan v4 that the designer ruled on 2026-10-25. A return meets, through
the Lead's direct edge from the phase the unit left, that edge's guard; otherwise the gate guards of the Lead's own
entries into the phase, for the unit's kind, against current state, pinning what the return relied on. A reconcile
meets no entry guard otherwise, by the plan's design. Each guard is
registered with its role (`gate` or `source`). A return that cannot be rechecked is refused, and every refusal's
details name the governed paths open instead. ADR-0003's amendment of 2026-10-25 records the rule and why the return
lives on `Gates`.

**Not built, by the ruling:** a policy switch between the options, records of the regressions a return makes, and
query forms for a non-mutating Ticket's review and verification guards. Such a Ticket's return to those phases is
refused and names its path: back to RUNNING, then the Lead's direct edge, which runs that guard.
