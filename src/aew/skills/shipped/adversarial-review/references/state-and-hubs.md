# State machines and hub routes

Read when the property depends on transitions, recovery, or concurrency. Establish state identities, transition guards, and record writers from the actual subject before building a model.

Trace one legal normal route, then relevant sequences such as authorize/queue/revoke/resume, effect/lost receipt/retry, or cancel/delayed completion. Record what is durable, what is volatile, and which entry becomes legal next. A transaction closes only the crash points and effects actually inside it.

For hub states, test whether an intermediate state lets a path leave a guarded region and re-enter with weaker checks. Identify a hub by supported incoming/outgoing routes and carried state, not by its name or absence of a phase field. Trace guard, identity, and evidence requirements across each composed route, including cycles.

Enumerate table edges, registration edges, and secondary effects/extra transitions. Distinguish what the declarative table permits from what the engine can produce. Record-writing rules, guard implementations, and reachable predecessor states may constrain the apparent graph; cite and verify those rules independently. A table-only path is not automatically a runtime exploit.

For a mechanical walk, derive edges from source and retain full keys and source locators. Assert unique identities and expose excluded edges. State whether the walk checks adjacency, reachability, or guard preservation; those are different claims. A seeded edge or known route can test the walk's blind spots without modifying the submitted subject.

Synthetic witness: a return transition checks only state name, while a detour through a recovery hub discards the generation needed at the effect. The finding requires evidence that the detour can actually write that hub state and then reach the return transition. If the engine records or revalidates the generation at commit, discard the bypass claim.
