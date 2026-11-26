**Built (`fix/e368-pack-truth-fixes`, #613): the truth fixes in what every worker is sent, on the operator's ruling of 2026-11-26, "ship truth fixes now".** This row's rewrite is not in it: no pack section is cut, moved or restructured. It claims delivery only. What a worker does with the text is measured by E389's Experiment A (the row filed by #604), not here.

Each false line of the worker-pack audit, checked against `main`:
- **F1 and F2** (a reviewer's archetype prose at the plan assessor's, the observation and the parent scope) were already fixed by E366 (#594). `test_a_roles_instructions_fit_its_scope` proves it over every role, scope and built-in card.
- **F3** (a role told to run tests with its shell) is fixed. The capability a check's evidence names as its method has one owner, `evidence.CHECK_CAPABILITY`, which the check runner and the validation run now take. A card's capability that one of its role's own operations serves (`evidence.OPERATION_CAPABILITIES`) is printed with that operation's command: "Capabilities an AEW command serves (it records the evidence you cite): targeted_test_execution (`aew check run <check-id>`)". It is no longer on the "no tool of AEW's serves (use your shell ...)" line. This holds for the verifier and for the implementers' cards. A card whose role has no `check.run` (a reviewer's) keeps the capability on the shell line, which is true of it.
- **F4** (the system text's "The first message is your AEW launch contract") is fixed. The sentence names the message's two texts, in order, by the heading each starts with, and each heading comes from its owner (`contract.RUN_HEADING`, `context.CONTRACT_HEADING`).

The pack-truth test (`tests/unit/test_pack_truth.py`) now sees both classes, over its whole matrix:
- no line of a pack sends a role to its shell for a capability one of its allowed operations serves, and each such capability carries the command;
- a run's system text, the third always-sent text, which the test did not read before: it says what the first message holds, prints only commands on the bridge and asks for no credential.

Each guard has planted cases. With the two fixes undone, 60 of the module's 504 cases fail.

Bytes, as a fact and not a result (the built-in cards on the test's synthetic inputs): the system text grows by 60 B for every role; the pack by 99 B for `verifier`, `python_engineer` and `c_engineer`, by 14 B for `engineer`, and by nothing for the others. The preamble is unchanged. A pack dispatched before this change and relaunched after it is refused by `launch.pack`, as after any change to pack text: dispatch a new invocation.

Left as they are, because none is false today:
- "This package is your complete, bounded context": true while nothing is behind a pointer. It becomes false with the rewrite, which must change it.
- "Evaluated snapshot" in an implementer's pack: the Contract's name for the pinned structure, and unclear there, not false.
- The skills lines: the pack's "Optional skills (load one only if ...)" beside the system text's "load each one", and the system text qualifying the pack's "Skills to load". Both are ADR-0006's adopted wording (amendment 2026-11-05), and the condition is per skill in both. One owner for them is the rewrite's (the audit's item 5). The pack-truth module's docstring no longer claims that no text corrects another: it states this as its limit.

**What remains** on this row:
- **The core-plus-pointers rewrite**, held as the treatment of E389's Experiment A: the duplicate text across the system text, the preamble and the pack, the map sent twice, the pointer to re-read after compaction, and the production size budget.
- **Its two design inputs from R0** (#604's note on this row): the pointers name what is not delivered and why, and the mandatory constraints stay in the core, never behind a pointer.
- **The other pack-truth extensions:** restated values in prose, the consistency of the three texts with every switch on, a size budget, and references that resolve from a worker's sandbox.
