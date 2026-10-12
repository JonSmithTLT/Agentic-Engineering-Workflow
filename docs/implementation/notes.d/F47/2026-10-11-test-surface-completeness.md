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
off `home`. A behavioural probe runs every surface declared `mutates: "no"` in process, against a synthetic sample
project, and fails it if anything under `.aew/` (bar the derived history index), a git ref or the working tree
changed. Of 43 such surfaces, 32 run to completion, 8 run only to a refusal on the sample, and 3 are exempt because
they are switched off there; `probe_coverage` lists the last 11.

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
