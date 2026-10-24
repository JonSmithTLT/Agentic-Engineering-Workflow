# Later notes on register rows

A note on a row of the [future-work register](../future-work.md) (or on its [decisions-due](../decisions-due.md)
item) is a file of its own here, never an edit of the row's Notes cell. Create it with

```
python tools/register.py note <row id>
```

which writes an empty `docs/implementation/notes.d/<row id>/<YYYY-MM-DD>-<branch slug>.md` and prints its path; write
the note there. It refuses a row the register lacks and a note that already exists.

- **`<row id>`** is the row's id exactly as its heading shows it (`F19`, `F15.5`, `E30`). The row must exist; it may
  be open or closed.
- **`<YYYY-MM-DD>`** is the day you write the note. Notes are read oldest first, by file name.
- **`<branch slug>`** is the branch's name in lower case, each run of characters other than `a-z` and `0-9` replaced
  by one hyphen, with none at either end: `impl/F9a_MS3` is `impl-f9a-ms3`. This is the one statement of the rule
  (`SLUG_RULE` in `tools/register.py`); `note` applies it to the checked-out branch. On a detached HEAD there is no
  branch, so pass `--slug <the branch the note will be committed on>`. A second note for the same row on the same
  branch and day goes into that same file.
- **The text** is Markdown: what you would have appended to the Notes cell, as one or more paragraphs. Relative links
  are relative to this file's directory (`../../adr/...`), and `tests/unit/test_docs_links.py` checks them.

**What is guaranteed.** Two branches whose slugs differ never write the same path, so their notes merge with no
conflict. Branch names that differ only in case or punctuation (`impl/f9a` and `impl-f9a`) share a slug; two such
branches noting one row on one day would collide, which nothing can rule out across unmerged branches, so do not name
branches that way.

**Why.** Almost every pull request appended a sentence to the same Notes cell of a hub row (F9, F15.5, F19, F20). Two
changes to one cell are a text conflict that no layout, no merge tool and no `register.py resolve` can avoid, and
GitHub, which runs no local merge driver, marks the pull request as conflicting. `future-work.md` does not inline the
notes: every row with an id ends with the same pointer to its directory, written whether or not the directory exists,
so adding a note changes no shared file.

**Recording something on a row means adding a note.** Where a plan, a design or a review says a deviation, a decision
or an outcome "is recorded in the register row" (the M4-E and F4 plans say so, for example), a note here is that
record; the row's cells change only when what they state changes (its work, its source, its target, its closing).

**Rows without an id** (the §1 gates and three closed rows: `E33 (part)`, `Q9 (decisions)`, `Q9 (reconciliation)`)
take no notes. Progress toward a gate goes in a note on the row that carries the gate's work (agent containment,
STG-05; network containment, F28); a gate's Condition changes only when the gate itself does.

**Build stages.** A build stage of the architecture map has one row (`STG-05`, `STG-12`), and each of its slices
notes on that row (designer ruling D-CS1-12, 2026-10-23).

**Capabilities built in slices.** A slice's progress on a capability of
[`implementation-status.md`](../implementation-status.md) that has no paragraph of its own there goes here, on the
capability's register row; the status page names that row in the capability's **Later slices** paragraph.

**Reading:** `python tools/register.py show F19` prints the row, its decisions-due item and every note, oldest first.

**Checking:** `python tools/register.py check` (and CI) refuses a note whose row is not in the register, whose name is
not `<YYYY-MM-DD>-<slug>.md` with a real date and a slug as above, whose text is empty, not UTF-8, not ended by a
newline or holding conflict markers, whose path differs from another's only in case, or which repeats another note of
the same row word for word. It reads the working tree, not the index, so a stray file here (a merge's `.orig`, an
editor's backup) fails `check` locally although CI, which sees only what is committed, would pass: delete it. That
is deliberate: a note written but not yet added is checked before it is committed.

The notes written into the cells before 2026-10-10 stay there.
