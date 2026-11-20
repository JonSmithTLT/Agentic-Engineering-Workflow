**A maps opt-out waits on I-6 (the maps switch-on, 2026-11-15).** With maps on for a new project, turning them off
(`maps.pack_slices: "off"`), or taking a declined switch offer later, goes through `aew manifest adopt`, which needs
the Lead credential with the Lead session ended (ADOPT_MANIFEST_EDIT). The switch offer only goes off to structural,
so the opt-out has no seat-free route until I-6 lands the operator's settings write path. A declined offer can be
asked again without the seat: deleting its row from `.aew/local/switch-offers.json` makes the next `aew opencode`
start ask. E331 removes the seat from the adopt route itself.
