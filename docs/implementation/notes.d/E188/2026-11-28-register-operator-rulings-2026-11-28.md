**The operator's decisions of 2026-11-28 on this row's triage** (R1, the scope, and S6).

**R1 is ruled.** The operator: "So R1 if the command can be copy pasted and gi e me the output. E.g., a command pre
finds and gives the shell command woth the id no thays not an ask thats what all commands should hopefully do. Gove
command with explanation from aew itself on what it does. Safe secure and i know exactly what it does. Thats not an ask
really." Read as a rule: in a runtime output, an id or binding value that the output fills in itself is not an ask; a
placeholder the reader must look up, where AEW could have found the value, still is.

**The scope is narrowed to O-IDS.** The operator: "So for now get ids in and words stays report onky until i can talk
with the designer. Track words seperatly and finish ids". This row's done condition is now O-IDS only, and its Work
and Source say so. O-WORDS stays in shadow (report-only) and is tracked as E402, blocked on DX3 (the refusal schema,
under F47.6) and on the operator's discussion with the designer.

**S6 is accepted as residuals for now.** The approval-binding placeholders (`plan accept` and `work accept` with
`--revision` and `--approval-digest`, `integrate publish --candidate`, `verify classify`, and the guide's lines for
them) stay as residuals. The operator: "For now their fine." Whether such approvals should move to G3 instead is E403.

**What remains:** the rule-precision pull request carries R1 into `vertical-uat.md` §8.2 as an amendment, with R2 and
R3 and a planted test for each; the text pull requests (S1, the free-text elisions, the values the engine knows); the
allow-list pull request, which removes the stale keys and records S6's placeholders under `residuals` with this
decision, and carries `operator-merge`; then O-IDS's flip to `enforce`. Nothing of that is in this register change.
