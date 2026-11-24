# Good: answer the path and stop

Synthetic task: explain which formatter serves `/summary` at source snapshot `demo-8`; source reads are permitted.

Current source:

```python
# routes.py
from formatters import plain, compact
HANDLERS = {"/summary": compact}

def serve(path, record):
    return HANDLERS[path](record)

# formatters.py
def plain(record):
    return "Name: " + record["name"]

def compact(record):
    return record["name"]
```

A derived graph from `demo-6` points from `serve` to `plain`.

Useful answer: “Observed at supplied snapshot `demo-8`: `routes.serve` selects `HANDLERS[path]`; `/summary` is registered to imported `formatters.compact`, which returns the name without the prefix. The graph describes `demo-6` and cannot establish the current edge. No execution was performed; this explains the supplied source, not a live deployment.”

The worker confirms the registration and imported implementation, resolves the contradictory evidence, and stops without inspecting unrelated routes.
