**What remains** (2026-11-26): one pull request's run on the flipped base. The When cell's condition has two halves.
**The nightly half is met:** the hand-dispatched nightly 45698876718 (`workflow_dispatch` on `ee89c341`, after O-CMD's
flip, #555, merged 2026-11-25T04:17Z) ran the full tier with `reference-assurance` green, so its ratchet decided stale
keys, and the ratchet step, which fails on a new or stale key of a rule in `enforce`, passed: neither O-CMD nor
O-SECRET was new or stale. It runs `nightly.yml` and the ratchet with `--event schedule --tier full`, as the scheduled
night does, so it counts as the nightly. (The scheduled nights 45575864672 and 45669941307 had `reference-assurance`
red, and decided nothing stale.) **The pull-request half is not yet met:** of the three pull requests open at the
flip, #560 and #561 ran CI on the flipped base before merging (runs 45547368206 and 45554780723), but #562, still
open, last ran at 2026-11-25T03:40Z, before the flip (run 45541550787). This row closes once #562 runs once on the
flipped base, or closes. **Done:** the tooling, #332; the rules, #335; O-SECRET in enforce, #502; O-CMD's triage,
#547, and its flip, #555.
