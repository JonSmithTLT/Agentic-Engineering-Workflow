# Bad: discovery metadata becomes proof

For the same synthetic task as the good example, an investigator reports: “The call graph proves `/summary` uses `plain`. The implementation therefore emits `Name: ...`. All formatting paths are covered.”

Why this fails:

- The graph belongs to an older revision and the current registration selects `compact`.
- A function existing in the repository does not establish that the route calls it.
- Neither a graph lookup nor a bounded source read proves all paths are covered.

Correction: use the graph as a search lead, confirm the dispatch and import against current source, and limit the answer to the supplied snapshot and question. Rebuilding every index or reading every formatter adds cost without resolving a remaining uncertainty here.
