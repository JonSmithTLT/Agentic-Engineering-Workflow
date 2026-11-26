**The reopen world and the Lead's first words (2026-11-26, branch `fix/v01-reopen-world`).** This branch covers
clusters C7 and C8 of the V-01 re-measure of 2026-11-26.
- **C7, the tool offers.** Every fresh-terminal reopen in V2 blocked for 300 s at AEW's tool-consent screen, because
  `ripgrep` was needed, missing and not declined. The takeover fallback followed. Q5 was answered by the operator on
  2026-11-26: "setup fixture that is recorded but not counted... AEW saying a critical item is missing isnt a ux
  failure its common sense. And yes it should count". So the offline world now settles AEW's tool offers in setup
  (`scripted_operator.settle_tool_offers`). It declines each tool offered, in a host-state directory of the world's
  own, and each decline is recorded as a `setup_fixture`, never counted. The seat-resume confirmation code still counts
  under `pin_reentries` on Linux. The ruling is quoted in `vertical-uat.md`, under the setup boundary.
- **C8, the first words.** The scripted Lead's status line was always `"words": null`, because it read only
  `structuredContent`. It now reads `resume`'s text, the MCP `content[0].text` (`aew.surface.readable`): the
  paragraph a person reads, before the JSON carried for a model. The JSON is never counted as words.
- **Measured locally (Linux).** In all five fresh-terminal V2 cases (four exit and kill cases, and forced mid-stage)
  the reopen reaches E330's seat resume. Each now shows takeovers 0, credentials 0 and `pin_reentries` 1 (the resume
  code). None leaves the Ticket INTERRUPTED or needs a reconcile, and the implementer's run is still running after
  the reopen. The first words name T-0001 through `resume`'s run line (`run: R-INV-0001-1 implementer T-0001:
  running`). The alpha's V2-forced line is gone.

**What remains** of STG-13 is V-01's other clusters. The alpha gate still fails on its V1 decisions line (C1, E335),
and every V2 case still fails strict on C12's fallbacks, the C1 to C4 counters and `pin_reentries` 1.
