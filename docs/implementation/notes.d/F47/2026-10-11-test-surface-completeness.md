**Anti-drift guard G1, the surface map** (operator approval, 2026-10-12): [`surface-map.yaml`](../../surface-map.yaml)
registers every `aew` command and typed Lead tool. Each entry has one intentional home (product, operator-admin,
recovery, diagnostic or internal), its users, the vertical UAT journeys that exercise it (evidence), a declared
`mutates` cross-checked against the code, and its known refusal codes. For each Lead-reachable command it also has
the Lead's door today (`typed`, proved by its primitive, or `shell-only (pending A2/A4)`) and its `lead_disposition`
(`typed`, `engine-owned`, `forbidden-to-lead`, or `undecided`).

`tests/unit/test_surface_map.py` (fast lane) checks the registry against the live parser, the live typed surface, the
primitive declarations and the vertical UAT's `IDEAL_PATH`.

- **Fails from day one:** an unregistered or vanished surface; a missing field; a mutating surface homed diagnostic; a
  `mutates` that contradicts the code; an unproved typed door; a missing disposition; an unregistered ideal-path
  command; an unknown error code.
- **Reported until its slice lands, which then flips its check to enforce** ([`surface-map.md`](../../surface-map.md)):
  - the projection's `owner` (A1);
  - structured refusals and the undecided dispositions (A2);
  - dispositions applied, and Lead shell lifecycle operations at 0 (A4).

**A label never exempts a surface.** Doors and dispositions key off `LEAD_REACHABLE` and the typed surface, never
off `home`, and whether the Lead's shell can reach a mutating command is decided by its mechanism (a credential,
`OPERATOR_ONLY`, an internal launcher, or a stated `lead_kept_out_by`), never by `users`.

A behavioural probe runs every surface declared `mutates: "no"` in process, against a synthetic sample project. The
sample has messaging and recall search on, and a Ticket assigned without a launch. The probe fails the surface if
any file under the sample's directory changed, bar derived indexes and git's caches. That covers `.aew/`, the
workspaces root, ignored files and `.git/`'s refs, config and worktrees.

- Each probe must run the real path (exit 0).
- A refusal is accepted only for the pinned, shrink-only `PROBE_LIMITED` list.
- A diagnostic home has no journeys.

Of 42 such surfaces, 37 run their real path, and 5 run only to a refusal on the sample (no harness run, no archived
record, no operator endpoint). `context pack` is declared mutating, proved on the sample by removing its pack and
running it.

**The end-state metric** (designer, 2026-10-12) is not one typed equivalent per command. It is every Lead lifecycle
need covered by typed or engine-owned behaviour, with Lead shell lifecycle operations at 0. Today 36 of the 48
Lead-reachable commands are shell-only and `undecided`. A2's plan decides each one, with its reason, and that decision
sets A2's and A4's scope.

**The standing rule** (operator, 2026-10-12), enforced by `new_surface` and stated in `CLAUDE.md`: every surface
added after the grandfathered baseline ships with its full entry and a decided disposition, which its code honours in
the same pull request. The baseline only shrinks.

**Slices that touch the registry:**

- B3 and C2 build `settings set` and `preflight`, and move them from `proposed` to `commands`.
- A4's sorting of the Lead-reachable commands updates their doors and dispositions.
