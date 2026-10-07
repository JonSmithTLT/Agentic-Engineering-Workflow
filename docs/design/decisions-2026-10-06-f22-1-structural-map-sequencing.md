# Designer decision of 2026-10-06: the structural map core and M4-H (F22.1)

**Status:** Decision record, governing. **Adopted** by the designer on 2026-10-06; it answers register F22.1's
decisions-due item (whether the structural map core, T5-A, is in M4-G/H). No further F22.1 design work is required.
§1 is the decision recorded as given; §2 says where it is filed.

## 1. The decision, recorded as given

> F22.1 — CLOSE / ADOPT
>
> T5-A structural mapping is permitted and preferred for M4-H if it is ready, because the structural map is part of the intended baseline project-navigation experience.
>
> It is not a prerequisite to M4-H and must not delay the value gate, preregistration, or dogfood.
>
> T5-B and later semantic/project-understanding slices remain out of the M4-H critical path unless a separate representativeness argument is made.
>
> From a design/sequencing perspective, T5-A is safe to implement in parallel because it is derived, non-authoritative state with its own map revision domain and does not own workflow legality, gates, publication, or control state.
>
> So the intended sequencing is:
>
> ```
> Main lane:
> M4-G → F25 → F19/Q7/U3 → M4-H
>
> Parallel lane:
> T5-A structural core
> ```
>
> If T5-A finishes and passes its own acceptance gates before M4-H, include it in the M4-H configuration.
>
> If M4-H is ready first, run M4-H without waiting for T5-A.
>
> No further F22.1 design work is required.

## 2. Filing (lead developer)

Register F22.1 is targeted as a parallel lane to M4-H: built when convenient, included in M4-H's configuration only
if it passes its own acceptance gates first, and never waited for. T5-B and later slices (F22.2, F22.3, F30) stay off
M4-H's critical path. F22.1's decisions-due item is removed. Ledger prefix SMQ.
