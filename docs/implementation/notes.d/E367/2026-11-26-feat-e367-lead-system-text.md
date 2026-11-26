**Built (`feat/e367-lead-system-text`, #599): the Lead's system text says only what is true and needed, and the typed `status` and `resume` results are compact.** The row stays open for what is the designer's.

What changed:
- **The system text** (`harness/opencode/projection.py`), measured with the pool gate's own render: 9,380 B to 6,193 B with messaging on, 9,121 B to 6,023 B off.
  - The three false lines are gone. The `--expect-rev` sentence is dropped: the guide's core already says it truly ("a command that takes `--expect-rev`"). "As the guide says" is gone too, since the core names the approval channels. The refused seat commands are now the broker's own list (`K.SEAT_COMMANDS`, which `lead_broker.CREDENTIAL_EMITTING` takes), so `aew lead handoff cancel` is no longer among them.
  - The tool line, which named every tool by kind, is dropped (the model has the listing). So are the facts the guide's core owns: never implement, a run ending is not progress, read with read, glob and grep, the free-text rule, and the revision a tool returns. Each now has one owner. The `aew guide` line goes as well (#593's m5); where no guide is appended, one line points at `aew guide core`.
  - A woken Lead gets one wake section, with its own timed-out line, in place of the wait section plus a line that overrode it (the audit's U1). One line says what to tell the operator, in place of eight.
  - The PowerShell form is told only to a Lead on Windows, which is never contained.
- **The tool list**, description-only within ADR-0017 D33's compact variant: 12,022 B to 11,974 B with messaging on, and unchanged off. The bare "free text" descriptions are dropped and `execution`'s is shortened. `resolve`, `message_send`'s `to`, `resolve`'s `subject` and `approval_digest`, and `integration_publish`'s `prepared_candidate` now say where their values come from.
- **The typed `status` and `resume` results** (`surface/run.py`, `_compact`), on E231's fixture: `status` 7,231 B to 3,282 B, below the shell's 3,520 B, and `resume` 9,596 B to 6,549 B.
  - `next_actions` is dropped where it equals the projection's hints.
  - The usage report is cut to its line, and the history audit to its breaches.
  - `run_problems` becomes a count.
  - Each role card keeps only its id and archetype.
  - `full` names the shell command that prints the whole report.
- **The pool:** 30,558 B to 27,323 B with messaging on. The 3,235 B saving lowers the baseline (system 9,020 to 5,833, MCP 11,900 to 11,852) and grows `operator_reserve` from 5,320 to 8,555 under the same words and date. The operator's 40,000 B cap stays.
- **The truth test** (`tests/unit/test_lead_text_truth.py`) runs over every rendered variant. It checks universal option claims against the parser and `LEAD_REACHABLE`. It checks that named commands exist, and that an operator's command is named only as refused here. Pointers must resolve, and each fact left to the guide must be in its core, said once. No line may override another. No offered enum value may be always refused unless it is pending the designer. Typed project reads must hold no large value twice, and `status` must cost no more than the shell's. Each guard has the audit's line planted, and on `main` it fails in 69 of its 72 cases.

What remains on this row:
- **The designer's decision** (decisions-due): the four schema changes (B1 drop `message_send.when`, B2 `explain.entrypoint`, B3 the stages' `execution` override, B4 `annotations`), and whether the MCP server's instructions count in the pool. Until B1, `turn-end` stays offered and refused. The truth test pins it as the one such value, and its description says so.
- **The `expect_rev` property descriptions** (about 500 B) are left to E329 (#596), which removes `expect_rev` outright.
