**Anti-drift guard G1, the surface map** (operator approval, 2026-10-12): [`surface-map.yaml`](../../surface-map.yaml)
registers every `aew` command and typed Lead tool with its users, the vertical UAT journeys that need it (or
`diagnostic`, or `unmapped` when a decision is owed), the Lead's door for each Lead-reachable command (`typed`, or
`shell-only (pending A2/A4)`, which makes F47.1's one-door gap explicit command by command) and its known refusal
codes. `tests/unit/test_surface_map.py` (fast lane) checks it against the live parser, the live typed surface and the
vertical UAT's `IDEAL_PATH`: an unregistered or vanished command or tool, a missing field, a Lead-reachable command
without a door, an unregistered ideal-path command and an unknown error code fail from day one; the projection's
`owner` (A1), structured refusals (A2), the shell-only doors (A2, A4) and the `unmapped` entries are reported until
those slices land, each slice then flipping its check to enforce ([`surface-map.md`](../../surface-map.md)). The
slices that build `settings set` (B3) and `preflight` (C2) move them from the registry's `proposed` list to its
commands; A4's sorting of the Lead-reachable commands updates their doors.
