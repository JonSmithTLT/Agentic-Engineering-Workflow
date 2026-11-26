**The reopen world and the Lead's first words (2026-11-26, branch `fix/v01-reopen-world`).** This branch covers
clusters C7 and C8 of the V-01 re-measure of 2026-11-26.
- **C7, the tool offers.** Every fresh-terminal reopen in V2 blocked for 300 s at AEW's tool-consent screen, because
  `ripgrep` was needed, missing and not declined. The takeover fallback followed. Q5 was answered by the operator on
  2026-11-26: "Q5 yup setup fixture that is recorded but not counted. The vertical was meant to fix ux issues. Aew
  saying a critical item is missing isnt a ux failure its common sense. And yes it should count but is that how aew
  works? I thought at that point it would automatically reattach already?" So the offline world now settles AEW's
  tool offers in setup (`scripted_operator.settle_tool_offers`). It answers the consent screen `none`, in a
  host-state directory of the world's own: each needed tool is declined (today `ripgrep`) and no optional one, and
  each decline is recorded as a `setup_fixture`, never counted. The seat-resume confirmation code still counts under
  `pin_reentries` on Linux. The ruling is also quoted in `vertical-uat.md`, under the setup boundary.
- **Open: the operator's closing question.** "is that how aew works? I thought at that point it would automatically
  reattach already?" It is not answered here, and nothing on this branch decides it. The current fact: a
  fresh-terminal reopen asks for the seat-resume confirmation code (E330), and that is the one `pin_reentries` each
  V2 case counts. An automatic reattach waits on `REATTACH_LEAD` reaching the wire: it is still a proposed command.
- **C8, the first words.** The scripted Lead's status line was always `"words": null`, because it read only
  `structuredContent`. It now reads `resume`'s text, the MCP `content[0].text` (`aew.surface.readable`): the
  paragraph a person reads, before the JSON carried for a model. The JSON is never counted as words.
- **Measured locally (Linux).** In all five fresh-terminal V2 cases (four exit and kill cases, and forced mid-stage)
  the reopen reaches E330's seat resume. Each now shows takeovers 0, credentials 0 and `pin_reentries` 1 (the resume
  code). None leaves the Ticket INTERRUPTED or needs a reconcile, and the implementer's run is still running after
  the reopen. The first words name T-0001 through `resume`'s run line (`run: R-INV-0001-1 implementer T-0001:
  running`). The alpha's V2-forced line is gone.

**The rows.** C7's and C8's register rows, E376 and E377, are filed by #601, not on this branch. Whichever of #601
and #603 merges second closes both rows and marks C7 and C8 `done` on `v01-burn-down.md`.

**What remains** of STG-13 is V-01's other clusters. The alpha gate still fails on its V1 decisions line (C1, E335),
and every V2 case still fails strict on C12's fallbacks, the C1 to C4 counters and `pin_reentries` 1.
