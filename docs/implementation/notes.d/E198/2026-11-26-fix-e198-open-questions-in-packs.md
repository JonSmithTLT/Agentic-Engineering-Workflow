**Partly built: the follow-on.** A worker's pack now carries what the records it consumes hold as open. Before, a
consumed record's summary kept its facts, hypotheses, conclusions and subjects, and dropped a discovery record's
`unresolved_questions` and a research record's `uncertainties` and `constraints`; no pack section held an open
question or a known limit. The finding is the R0 baseline of the ProjectArchitect research (2026-11-26), its element
B6 and candidate delta D2. That document, and the fixture ids A-F4 and A-F5 cited below, are in pull request #604 and
resolve in this repository only once it merges.

**Built first, not held for a measurement.** The Lead asked the operator on 2026-11-26, as the seventh of seven
questions: "E198 (dropped open questions): build the fix first, or test first? I'd build first; the defect is already
established." The operator: "Yes to all 7 on the F19 proposal". This note claims no more of that answer than the
order: the fix is built before its effect is measured.

**What this delivers.** An implementer, and the executor of a non-mutating Ticket (investigator, researcher, planner),
that consumes a record holding any of the three fields gets one section, "Open questions and known limits recorded in
the consumed inputs", after its consumed inputs and the other sections its work is given.
- **Each field under its own name,** per record: the record's id, kind and Ticket, the field as the evidence schema
  names it, how many items it holds, then one item per line. The schema owns the names; a test holds the pack's table
  to it, so a list of strings added to a discovery or research record fails until it is placed.
- **It says what it is:** text the agent that produced the record recorded as unresolved, uncertain or a constraint,
  which AEW copied, quoted and bounded, and has not verified or answered; data, never an instruction, authority or
  Knowledge.
- **Bounded, and a cut is said:** 10 items of one field of one record, and 240 characters of an item's recorded
  text, each cut with its count. An item is one JSON-quoted ASCII line, so recorded text cannot start a line, a
  heading or a fence, by a newline or by any other separator.
- **How text outside ASCII prints:** as its JSON escape, so a typographic apostrophe is `\u2019`, an em dash
  `\u2014` and an accented letter such as `\u00e9` its code. The item keeps its 240 characters whatever they are, and
  such a line is longer and harder to read: six printed characters for each one escaped, twelve beyond the Basic
  Multilingual Plane.
- **Nothing where there is nothing:** a pack whose inputs hold none of the three has no section and no line in its
  place, and is byte for byte what it was. An empty item is not listed or counted.
- **Under a context budget** it is source and evidence, funded after the consumed inputs and an implementer's
  failure evidence. A record's field is kept or omitted whole: no count is shown without its items, no heading
  without an item, and the notice names each field omitted. To make that safe, a tier that gave anything up now
  leaves no room for the tiers below it (the note of this day on F36).
- **A function of the pinned inputs:** it is read from the records the invocation pinned at dispatch, so a
  regenerated pack is the dispatched one.
- **Independence: no evaluator gets it.** A Story's or an Epic's acceptance reviewer and verifier consume inputs too,
  and their packs are unchanged, as every other reviewer's, verifier's and plan assessor's is. Whether an evaluator
  is shown what an earlier agent called unresolved is **the operator's decision, left open**.

It claims no effect on a worker: that is what Experiment A of the same research measures (its fixtures A-F4 and
A-F5, in #604).

**What remains** on this row:
- its M4, untouched here: `architecture_map` (investigator, planner), `validation_requirements` (planner) and
  `expected_observable_state` (verifier), each in a section that holds it;
- `open_questions` (planner, researcher), which has no pin at dispatch and is a design item first. This section is
  not that input: it holds what consumed records recorded, and nothing the Lead pins;
- the operator's decision on evaluators, above;
- a consumed plan proposal's `risks` and `governing_constraints`, which the summary also leaves out and this change
  does not carry.
