**Candidate: per-field descriptions in the execution policy's schema (found building F46.1, slice F1a).** This row
asks every operator-editable setting to show its description, and the F46.1 proposal (§2) assumed
`src/aew/schemas/execution.schema.json` carries "a class and a description per field". It carries a class per field,
but descriptions only on its blocks: `containment`, `steering`, `steering.envelope`, `notify`, the switch sections and
the `profile` definition. No projected field has a description of its own. F46.1's projection emits a field's own
description or none, never an enclosing block's, because a block's text shown under one of its fields tells the
operator something about another field (`model`'s text under `max_steps`, for example). The configuration page
therefore shows no per-field help until the schema gains a `description` on each operator-editable field. That is a
schema change for the schema's owner, needed before F46's editors (F46.2 onwards) can show "its current value,
description, valid values, …" as this row's Work requires.
