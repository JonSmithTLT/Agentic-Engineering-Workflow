# Later notes on register rows

A note on a row of the [future-work register](../future-work.md) (or on its [decisions-due](../decisions-due.md)
item) is a file of its own here, never an edit of the row's Notes cell:

```
docs/implementation/notes.d/<row id>/<YYYY-MM-DD>-<branch slug>.md
```

- **`<row id>`** is the row's id exactly as its heading shows it (`F19`, `F15.5`, `E30`). The row must exist; it may
  be open or closed.
- **`<YYYY-MM-DD>`** is the day you write the note. Notes are read oldest first, by file name.
- **`<branch slug>`** is your branch's name in lower case, every character other than a letter or a digit replaced by
  a hyphen, runs of hyphens collapsed: `impl/f9a-ms3` is `impl-f9a-ms3`. Branch names are unique, so no other change
  writes your file. A second note for the same row on the same branch and day goes into that same file.
- **The text** is Markdown: what you would have appended to the Notes cell, as one or more paragraphs. Relative links
  are relative to this file's directory (`../../adr/...`), and `tests/unit/test_docs_links.py` checks them.

Why: almost every pull request appended a sentence to the same Notes cell of a hub row (F9, F15.5, F19, F20). Two
changes to one cell are a text conflict that no layout, no merge tool and no `register.py resolve` can avoid, and
GitHub, which runs no local merge driver, marks the pull request as conflicting. A new file at a path no other
branch writes merges by construction. `future-work.md` does not inline the notes: every row with an id ends with
the same pointer to its directory, written whether or not the directory exists, so adding a note changes no shared
file.

Reading: `python tools/register.py show F19` prints the row, its decisions-due item and every note, oldest first.

Checking: `python tools/register.py check` (and CI) refuses a note whose row is not in the register, whose name is not
`<YYYY-MM-DD>-<slug>.md` with a real date, whose text is empty, not UTF-8, not ended by a newline or holding conflict
markers, whose path differs from another's only in case, or which repeats another note of the same row word for
word.

The notes written into the cells before 2026-10-10 stay there. A row's cells still change when what they state
changes (its work, its source, its target, its closing); a note never rewrites them.
