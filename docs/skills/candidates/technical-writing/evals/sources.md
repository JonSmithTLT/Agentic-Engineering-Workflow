# Research and selection

Evaluator-only. Primary sources inspected 2026-10-12. This is an original synthesis, not a measured ranking of writing skills. Live sources may change; freeze source snapshots and runtime bytes before comparative evaluation. External skills were read as research, not installed or executed.

| Source | Retained | Deliberately excluded |
|---|---|---|
| [StrictDoc technical-writing skill](https://github.com/strictdoc-project/technical_writing_skill/blob/main/SKILL.md) | Put the useful conclusion early, preserve precision, and check a rewrite again. | Activation banners, exhaustive per-sentence rule passes, blanket punctuation/word-form bans, and fixed sentence targets. |
| [Plain-writing skill](https://github.com/docwriter-org/plain-writing-skill/blob/main/skills/plain-writing/SKILL.md) | Concrete language, connected paragraphs, stable terminology and removing empty emphasis. | Universal no-analogy/no-dash rules, fixed clause/list limits, and style preferences that can distort technical meaning. |
| [Google audience guidance](https://developers.google.com/tech-writing/one/audience) | Write for the reader's existing knowledge and task rather than the author's familiarity. | An obligatory audience interview when context already supplies the answer. |
| [Google short sentences](https://developers.google.com/tech-writing/one/short-sentences) | Split overloaded ideas and remove unnecessary words. | Treating the shortest possible sentence as the goal or breaking causal connections for a word count. |
| [Microsoft style and voice](https://learn.microsoft.com/style-guide/top-10-tips-style-voice) | Direct wording, important information first, visible choices and useful next steps. | Brand-specific punctuation/capitalization rules and an unconditional shorter-is-better rule. |
| [Diataxis](https://diataxis.fr/) and [explanation](https://diataxis.fr/explanation/) | Distinguish learning/understanding, task instructions and reference lookup; explain causal context when understanding is the task. | A mandatory four-document architecture for a short reply or small project. |
| [Home Office effective documentation](https://engineering.homeoffice.gov.uk/patterns/write-effective-documentation/) | Reader needs, accessible language and maintained, useful documentation. | Organization-specific templates or treating specialist audiences as needing dense prose. |
| [GOV.UK error messages](https://design-system.service.gov.uk/components/error-message/) | Explain the problem and an actionable correction; match the message to the actual failure. | Applying field-validation remedies to service failures or inventing an action unavailable to the reader. |

The sources differ on sentence length and stylistic rigidity. This candidate chooses reader comprehension and fidelity over universal bans. It permits technical vocabulary when precise, causal sentences when connected, and analogy when it helps without misrepresenting the mechanism. No claim about text being human-authored or evading detection is part of the skill.

The supplied technical-writing evidence reports qualifier loss, overstated mechanisms, stale/manual fact copies, wrong-audience messages, ambiguous notation and excess history. Those observations motivate source/claim checks and pilot cases. They are retrospective reports, not controlled evidence that this candidate improves outcomes. Project-specific output restrictions and workflow rules were excluded.

## Normative-language refinement, 2026-10-13

[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) ground the conditional keyword guidance. Retained: distinctions among requirement, qualified recommendation and option, plus uppercase keyword interpretation where BCP14 applies. Excluded: assuming SHOULD/MAY are explanatory, imposing that vocabulary universally, or equating typography with adoption authority. The supplied designer review motivates the artifact/status distinction and four cases; its proposed source taxonomy is used as descriptive roles, not a universal document precedence rule.
