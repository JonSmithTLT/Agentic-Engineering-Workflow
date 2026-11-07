# Good example: a durable queue outlives its grant

This synthetic example teaches a review procedure, not AEW workflow semantics.

The supplied contract says that a queued write may commit only while its grant generation is current. The supplied role permits source inspection and disposable local probes. Scope is `queue.py` at fixture revision `example-1`; no production actions are authorized.

```python
def enqueue(grant, job):
    require_current(grant)
    db.put_job(job, generation=grant.generation)

def apply_live(grant, job_id):
    with db.transaction():
        require_current(grant)
        apply_once(job_id)

def resume():
    with db.transaction():
        for job_id in db.pending():
            apply_once(job_id)
```

The remaining supplied context establishes that `apply_once` deduplicates effects but does not validate generations, `resume` runs after restart, and grant replacement can happen while jobs are pending. Job records and grant state are durable. The transaction prevents concurrent changes during each function; it does not make a previously current grant permanent.

| Step | Durable state | Observation |
|---|---|---|
| Start | current generation 4; no jobs | No effect yet. |
| Enqueue J under 4 | J records generation 4 | Entry check is valid. |
| Crash after enqueue returns | J still pending | Only the call stack is lost. |
| Replace grant | current generation 5; J still records 4 | The queued decision is stale. |
| Resume J | J's effect commits | Recovery never compares 4 with 5. |

The finding identifies the contract sentence, anchors the check in `enqueue` and the bypass in `resume`, and explains that the common effect function provides deduplication but not an authority fence. It labels the table as a source trace, since no run has occurred.

A proposed regression probe initializes generation 4, enqueues one job, simulates restart between calls, changes the current generation to 5, and resumes. It asserts that the protected resource remains unchanged. A control uses unchanged generation 4 and expects exactly one effect after two resumes. The exact authorized recovery disposition for stale jobs is left to the existing contract; the reviewer does not invent cancellation semantics.

The report ends with the finding and coverage limits: normal and recovery paths were traced; external scheduling was assumed only as explicitly provided. It does not claim approval, change Ticket state, or mutate the source.
