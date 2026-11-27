**Built: the consumed inputs' summaries, and the other sections that print a worker's recorded text, quote and bound
it, as #614 does for recovery items and #621 for recorded open items** (the operator, 2026-11-27: "The pack text fix
CAN be done now"). Before, `_input_summaries` (`src/aew/engine/context_ops.py`) built `fact: …`, `hypothesis: …`,
`conclusion: …`, `subject: …`, `objective: …` and `approach: …` lines from the record's strings, and the pack printed
them as they were; the evidence schema bounds none of them to one line or a length, so a statement of several lines
already broke the input's list.

**What changed, section by section** (`src/aew/knowledge/context.py`):
- **Consumed inputs:** each summary item is now the record's values by label, and the pack prints each value through
  `_quoted` and `bounded_text`, cut to `RECORDED_MAX_TEXT` (480 characters as printed) with the cut counted
  (`recorded`). A research subject prints its name, version and source as three quoted values. A line under the
  heading says what the values are.
- **Failure evidence** (an implementer's pack): each claim's text and the verifier's suspected cause, the same way.
- **Implementation facts** (a reviewer's pack) and **implementation revision** (a verifier's): each file changed,
  check run, deviation and unexpected finding the implementer reported, the same way.
- **Record under review:** printed whole, as the reviewer or verifier judges it, its fields and now its body each in a
  fence longer than any run of backticks in them (the fence the historical records already took, now `_fence`).
- **Child work, and the change under review:** a child's diff, the aggregate diffstat, the reviewer's diff and the
  verifier's diffstat take the same fence. Its titles are a work unit's title, left as below.

**Bytes:** every pack whose consumed inputs carry a summary changes. On `tests/unit/test_pack_truth.py`'s synthetic
inputs, every built-in role and card with inputs grows by 177 B (the line on what the values are, and the quotes on its
one value), and every pack without inputs is unchanged. Beyond those inputs: 2 B a printed value, the JSON escape of a
character outside ASCII or a control character, 16 B for a record-under-review body's fence, and a fence of four or more
backticks only where the content holds a run of three. A pack dispatched before this change and relaunched after it is
refused by `launch.pack`, as after any change to pack text: dispatch a new invocation.

**Left, and filed as E401:** an open finding's summary and location, a work unit's title, and the documents a pack
prints whole as Markdown (a requirement's body and criteria, an ancestor's, the accepted plan). The rest of this row's
work is unchanged: its M4, `open_questions`, the operator's decision on evaluators, and a proposal's `risks` and
`governing_constraints`.
