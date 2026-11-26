Batch 4, the evidence group, by the operator's answers of 2026-11-26 to the three questions batch 3 left (ADR-0006, amendment 2026-11-26, the fourth batch).

- **On where `empirical-evaluation` and `ci-evidence-triage` go:** "Your rec is fine on 2". Both ship from AEW's install, labelled unevaluated, each after its public-text check, byte for byte from its public candidate (`SKILL.md` and `references/`, without `evals/`). All as `optional_skills`: `empirical-evaluation` on `researcher` and `investigator`; `ci-evidence-triage` on `verifier` and `code_reviewer`, and on the Lead's own list (the manifest's `lead`, E161).
- **On `frontend-design`:** "for 3 we should just track making a front-end focused specialized role card. It'll also align with the mcp servers and utilities we were planning on jnckuding anyway." It stays unserved, and the card is E395. It is no longer this row's.
- **On a foundational skill per role:** "4 yes it was planned for all role cards to have 1 foundational skill. The size it adds is probbaly negligible but jt adds the final layer of how a specialized role should behave. We have context packs which is what the job is, knowledge system which is what have previous agents learned, and skills are how you should proceed going forward with all the knowledge". So every built-in card gets exactly one skill in `skills:`, with no measuring run first.
- **Measured, not capped** (bytes, before and after):
  - a run's copied skills: `researcher` none to 8,365; `investigator` 33,965 to 42,330; `verifier` 28,173 to 35,307; `code_reviewer` 68,951 to 76,085;
  - a run's system-text skill lines: `researcher` none to 100; `investigator` 191 to 215; `verifier` 293 to 315; `code_reviewer` 333 to 355;
  - the Lead's system text, on every request: its skills line grows by 22 bytes (184 to 206 contained, 279 to 301 not), and its copy from 23,247 to 30,381;
  - the Lead guide's staffing section is unchanged at 728.

**What remains** on this row:

- **The foundational skill for each card, as a mapping the operator approves.** Seven of the twelve cards already hold exactly one skill in `skills:`. The proposal for the other five (`engineer`, `investigator`, `planner`, `plan_assessor`, `researcher`) is with the operator, and no card's `skills:` changes until it is approved. `researcher` has no fitting skill yet.
- **`agent-security-review` and `security-control-validation`** on `security_reviewer` (the designer's fit, 2026-11-04), still waiting on the operator's update of the two candidates from their final drafts (#563's N2; this row's note of 2026-11-25).

Neither waits on E135's evaluation runner.
