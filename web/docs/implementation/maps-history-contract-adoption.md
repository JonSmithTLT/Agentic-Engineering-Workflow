# Maps/history contract adoption — W1

Date: 2026-10-10. Source baseline: merged `60a26c398dfd37dd2e5101d4e4ab09633838db99`, including S0 #161 (`6f8cc28`). The operator reported S0 merged and had previously authorized the reviewed workstream.

## Contract disposition

[Fresh-context C0 review](../c0-review-main-line-0.1.3.md) accepts canonical artifact SHA-256 `417fa77739a006d65605737794efa6b957c68b6cecd9f6a4d0fd1869272187fb`. This is an artifact-bound review of uncommitted bytes, not a claim that the source baseline contained them. The exact committed implementation receives its own AGENTS review before publication/merge.

Appendix A is applied without wire amendments. `integrated` is added only to the existing open-string annotation and matching displays. Existing 16 paths and envelopes remain 0.1.2. Six new GET/HEAD proposals carry 0.1.3. The approval history retains the 0.1.2 ACCEPT and its exact original digest/commit; the packaged frontend baseline remains unchanged.

## Implementation

Generated accepted types cover the additions. A bounded, fail-closed generator produces only the additive runtime schema family and its referenced scalar/reference definitions from the canonical artifact; unsupported schema keywords fail generation. The offline gate checks byte-for-byte generator output. Existing reviewed handwritten parsers remain unchanged except an envelope helper with a route-specific literal version defaulting to 0.1.2. New parsers are exposed in the demo Contract Playground registration, keeping them out of existing page startup imports.

Pure request builders validate full object IDs, roots, page bounds, repeated literal search terms/kinds, total term character count, encoded query size and dates. They issue no reads. Search scheduling, capability disappearance, lifecycle ownership and page UI remain implementation obligations after S2. No new page, automatic search, polling policy, or production route navigation is introduced here.

The fictional `maps-history.json` fixtures are parser/contract samples for all six responses, including no-map and empty/incomplete search; they are not served Engine projections or evidence of live behavior. Existing worker and HTTP demo worlds retain their original 0.1.2 payloads and share the adopted contract manifest identity. Integration fixtures/projectors become interactive in the separately gated UI checkpoints.

## Verification and remaining gates

The main-line schema compiler and compatibility checker report no problems against vendored 0.1.2. C0 independently ran 56 contract tests and annotation/name-preservation probes. Targeted frontend tests cover old/new envelope rejection, bounded collections/counts, strict unknown-field rejection, open semantic strings, Unicode lengths, repeated parameters and invalid identities.

Pinned Node 22 offline gate, clean exact-commit freeze, applicable browser regressions and independent exact-head implementation review must complete before merge; results are recorded in the checkpoint evidence rather than assumed here. S1/S2 remain prerequisites for the Maps/Search pages, and S3 needs a separately agreed package baseline and authenticated live acceptance. No Engine work records or backend adoption are created by W1.

Preliminary validation: pinned Node 22 offline gate passed 192 tests, typecheck, lint, artifact checks and both builds. Main-line contract/note/static tests passed 119 tests with one file-symlink platform skip. A sandboxed static-test trial could not create its temporary directory junction; the unsandboxed repeat passed. First offline failure (generator depended on a vendored test fixture outside the frontend-only build context) and second failure (two legacy-only test expectations) are retained; generation now follows the new response dependency graph directly and legacy assertions remain scoped to 0.1.2 envelopes. The committed-source gate supersedes these preliminary working-tree results.
