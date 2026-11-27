# Check selection and failure handling

Use the least costly supported check that observes the acceptance criterion via
the affected interface. A focused check can be faster and easier to attribute
than a broad suite. Add the next check when it exercises a distinct caller,
dependency, persisted state or integration path the first misses. The plan
and repository determine required broader checks.

| Observation | Next action |
| --- | --- |
| Check passes both baseline and edited state | Establish whether the baseline already meets the criterion or the check cannot distinguish the change. |
| Edited state has a new failure | Stop adding behavior. Keep the observation, isolate the first affected step and diagnose. |
| Baseline and edited state show comparable failure | Keep both results. Explain the extent of the supporting comparison and any outstanding impact. |
| Check is unavailable | Record not run, the exact missing capability and the evidence still available. |

Use existing setup and known inputs. Validate that a fixture reached the
path you expected and any comparison ran under comparable conditions.
Preserve the earlier attempt when retesting. Do not reset a worktree to
obtain a baseline unless its ownership and the operation are authorized.
