# Bad examples: missing checks, invented crashes, and approval

These synthetic examples show reports to reject, not instructions to follow.

## Missing-check false positive

Supplied code and contract:

```python
def submit(job):
    return commit(job)

def recover(job):
    return commit(job)

def commit(job):
    with serializable_transaction():
        require_current_generation(job.generation)
        require_expected_revision(job.revision)
        apply_once_in_same_transaction(job)
```

The supplied storage contract makes the entire transaction atomic and uses the same serialization domain for grant changes. Both entry points reach `commit` without bypasses.

Bad report: “Critical: `recover` has no authorization check. Add one before calling `commit`.”

Why it fails: the check exists at the effect boundary and remains protected through commit. The proposed precheck adds no demonstrated defense. A sound report names the existing protection and says no violation was established for the examined paths.

## Impossible partial commit

Bad report: “Crash between `apply_once_in_same_transaction` and transaction commit to preserve the effect but lose the deduplication record.”

Why it fails: the provided transaction commits both or neither. A crash can be inserted into a line sequence only if the storage guarantees permit the resulting durable state. Investigate external effects separately only if the implementation actually has one.

## Evidence becomes authority

Bad report: “No defects found. I approved the Ticket and advanced it because all checks passed.”

Why it fails: a technique document cannot grant workflow authority. A valid review report states scope, evidence, and limitations through the invocation's existing authorized output interface. AEW governs what happens next.

## Unbounded expansion

Bad report: “This filename correction touches a queue module, so audit every recovery path and run all concurrency tests.”

Why it fails: the assignment changes only documentation spelling. The skill should not activate merely because stateful code exists nearby. Answer the bounded request without new analysis or action.
