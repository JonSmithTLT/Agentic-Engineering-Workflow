# W01 backend question ledger

All entries are OPEN integration questions. Owner names are roles, not an assertion
that someone has accepted an assignment. A working fixture is not a backend answer.

| ID | Question / evidence needed | Owner role | Live blocker |
|---|---|---|---|
| W01-Q01 | What signals authoritative bootstrap and authentication/permission changes? How should the frontend invoke its explicit session reset? | Main API/authentication owner | Automatic authenticated session isolation |
| W01-Q02 | Which project/worktree/attempt inputs affect each projection, and how are authorized scopes selected? | Main read-projection owner | Multi-scope live reads; W01 adds no query fields |
| W01-Q03 | Which historical snapshots are retained/readable, and how is unavailable history reported? | Main history/read owner | Pinned historical comparisons |
| W01-Q04 | ETags must cover represented revision and request scope. Confirm conditional GET behavior, including anomalous validators. | Main API caching owner | Real validator correctness; a 304 cannot disclose unseen live revision |
| W01-Q05 | Who owns each future Journal/context/guarantee schema and its canonical version/digest review? | Main M6/API owner | Future preview adoption; W01 defines no domain schemas |
| W01-Q06 | How are denied records filtered before delivery, and which diagnostic identities may be disclosed? | Main authorization owner | Real permission acceptance; browser hiding is insufficient |

When resolved, record the accepted artifact/version/digest/commit and reviewer.
Do not mark integration accepted from frontend tests or authored demo permissions.
