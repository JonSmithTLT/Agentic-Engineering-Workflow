**The default is 2** (ADR-0003's amendment of 2026-11-07): `init` writes `mutating_concurrency: 2` into a new project's
`gates.yaml`, and a `gates.yaml` without the key reads the same default through `mutating_cap`. An existing project
keeps the value its `gates.yaml` holds; the offer to switch it, at the operator's own terminal, is this row's next and
last step. The proof is `tests/regression/test_concurrency_two.py`: two Tickets whose scopes can meet are held by the
launch conflict check (E151), and two whose scopes cannot both run and integrate one after the other through the
queue's lease. **The gate:** "after first use" was the operator's decision of 2026-11-06. Asked on 2026-11-07 whether to
keep it or lift it, the operator answered "i would obviously want this done. yes." and had the work started that day;
the Lead recorded that as lifting the gate. **Correction:** the Notes' "Still open in M4-D: the `checks` validation path (D5, register D4)" is
stale: M4-D5 built it on 2026-10-05, which closed D4.
