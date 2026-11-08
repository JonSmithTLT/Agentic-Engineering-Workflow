**Measured (one live turn, 2026-11-07).** The live usage meter holds on OpenCode 2.2.6 for OpenCode Zen's Responses
route: a contained run of `opencode/gpt-5.6-luna` through AEW's provider relay made 2 calls. Split into disjoint parts,
Zen's usage equals the meter's final sample in every category (input 241, output 80, reasoning 115, cache read 2163,
cache write 3427; 6026, the calls' total), and its per-call `cost` sums to the meter's provider cost. Zen's
`input_tokens` counts cache reads and cache writes, and its `output_tokens` counts reasoning. The route is declared
`disjoint` in `OpenCodeAdapter.token_semantics`, with the calls as the fixture `usage-2.2.6-opencode-responses.json`.
Zen's other routes stay `unknown` until each is measured (E209). The source re-reads this row names are still owed.
