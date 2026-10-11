The register's remaining conflicts were two changes appending to the same Notes cell of a hub row, which the
row-by-row layout and `register.py resolve` cannot merge and GitHub shows as conflicting. A note is now a file of its
own under `notes.d/<row id>/` ([the convention](../README.md)); every row with an id renders the same pointer to its
directory, so adding a note changes no shared file. `register.py show <id>` prints a row with its notes; `check`
validates them. Proved in `tests/unit/test_register.py` and, with real git merges, `tests/unit/test_docs_merge.py`.
