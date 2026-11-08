**Owed by the next step (the PR that turns the switch on at init and regenerates at each publish), from the first part's
independent review.** None does harm while the switch is off. Each lands no later than that PR.

- **The slice's reach beyond the pack, first because it is what the cost concern hits.** A dispatch's output returns `pack`
  whole, so the slice's body stays in the Lead's context for every later request, now for every card's non-Ticket dispatch.
  Each invocation's pinned entry also sits in `control.yaml`, which every transaction rewrites, until its unit is
  archived. The per-card record above counts neither. Fix: return `pack` without `slice`, since the Lead needs its path
  and hash, and add the state growth to the record. The pin itself stays.
- **The size record.** "The worst case" above is one repository's figure, which has 3 hints. Filling the 40-row and
  20-hint bound gives about 5,120 characters with short names and 8,070 at 60-character names, and a STALE map adds up to
  about 400. There is no byte bound. The record needs those figures and a command to re-measure them, and `ROWS, HINTS`
  need a named source.
- **Init's map goes STALE once `.aew/` is committed,** since the map's path listing doesn't exclude `.aew`. Decide:
  regenerate on the first commit, or leave `.aew/` out of the listing, which makes every map STALE once. State it in
  ADR-0015's amendment meanwhile.
- **A project that had already turned the switch on** gets the slice on every card at its next pack, with no notice. The
  shared switch offer should say so.
- **The time init spends on the map.** About 5 s at 100,000 paths on a loaded host, before the report, with each git
  process bounded at 300 s. An interrupt in that window loses the report and the consent screen, and init then refuses.
  State the limit in the amendment, and correct the quickstart's "may run again" for this window.
- **The never-fails proofs stop short of the command.** Add one CLI test: `aew init` in an empty repository exits 0 with
  `map.reason == "no_commit"`.
- **The pack's notice points workers at `aew map show`,** whose surface-map users are the operator and the Lead, and which
  returns the whole record. List workers as users, or drop the pointer.
- **`already_selected` also labels a leftover registry that selects no structural map.** Only a leftover `local/maps`
  reaches it.
