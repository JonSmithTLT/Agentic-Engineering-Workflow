**A correction to S12-2's last note** (`2026-10-25-feat-s12-2-module-page.md`, from #268). That note gives "final
counts" (1043 records) and calls `index.json` byte-identical to `main`'s. Both held at #268's base only. The reference
is generated from the code, so every later change to what it enumerates changes the counts, and none of them is final.

- **The counts at a commit** are `python tools/reference.py counts` there. They are derived, never restated.
- **For example, at `c81eb233`** (after #271, #272, #269 and #274): 1074 records, 401 complete-by-construction and 673
  lower-bound, 92 unresolved items, 185 modules, digest `sha256:bcf9f33f…a34a`.
