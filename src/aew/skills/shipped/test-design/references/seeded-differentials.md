# Comparative and non-narrowing guarantees

Use when a change claims unchanged behavior, broader coverage, or protection that never narrows.

Freeze the relevant base implementation and its environment; apply the same deterministic seeded corpus to base and changed subjects. Define the relation from the contract: equality, subset/superset of protected items, or another semantic ordering. Output length alone rarely expresses a protection guarantee. The baseline characterizes prior behavior, not independent correctness; keep contract-derived valid and invalid controls too.

Cover representation variants, boundary lengths, encodings, channels and state transitions that can change the relation. For projections, inspect every relevant output channel, not only the main return value. Keep corpus identity, seed, actual differences and minimized counterexamples. Source/generated input and its final rendered form may require separate checks.

Challenge each independent defense with an isolated ablation or planted fault. Predict which check should reject it before running, then verify the mutant actually exercises that mechanism. An invalid near-miss for every accepting exception detects a judge that passes by construction. Restore exact bytes and verify hashes, or discard the isolated fixture; never reset dirty working files.

A fixed seed makes a run reproducible, not exhaustive. Report explored domain, unsupported forms and missing platform coverage. A surviving mutant may expose a weak test, an ineffective mutation or an alternate defense; inspect which before claiming a test gap.
