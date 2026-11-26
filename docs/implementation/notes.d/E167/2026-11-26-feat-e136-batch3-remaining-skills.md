Built with E136's third batch (ADR-0006, amendment 2026-11-26).

- **The card.** `technical_writer` extends the implementer archetype with `technical-writing` in `skills:`, so every run of it is told to load the skill and its pack's `sources` pin it. Its capabilities are the archetype's own, and it narrows nothing. Generated reference stays out of reach as it is for every implementer (the archetype bars generated paths); the card says to report a needed change to it.
- **The reviewer.** `code_reviewer` offers `technical-writing` in `optional_skills`; there is no document-review card.
- **The Lead's staffing section** is derived from the implementer cards, so it now names `technical_writer` with its `use_when`. Its last sentence named what "every implementer card" offers; the writer card offers no optional skill, so the sentence now names the cards it is true of (`guide.staffing_text`).
- **Checks** are the project's own configuration, proposed from the map and adopted by the operator. Nothing is built for them here.
- **Not exercised on a model.** No run has used the card. SYS-45's finish line keeps the real run that ends with a document the operator reads, and qualification stays owed (E135).
