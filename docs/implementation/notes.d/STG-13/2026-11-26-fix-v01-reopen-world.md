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

**What remains** is the product gap C8 found. The readable head of `resume` does not name the open Ticket: on a
project whose T-0001 is RUNNING, it says `resume: done (project)` and the project's next step. V2's "told where things
stand in words" check, which wants T-0001 in the first words, therefore still fails until `resume`'s readable text
says where the work stands. The rest of STG-13 is V-01's other clusters.
