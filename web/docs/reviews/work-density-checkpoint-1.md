# Work cleanup checkpoint 1 — implementer review packet

Plan: `web/docs/design/plans/work-density-cleanup.md`. Baseline review: `web/docs/reviews/page-density-2026-10-04.md`. Register: E16 in `docs/implementation/future-work.md`.

Operator authorized planning and incremental improvements on 2026-10-04 while Knowledge/API designs settle. This packet covers the first bounded improvement; independent acceptance remains pending. No backend, Knowledge or preview contract adoption is proposed.

## Change and exact source

Runtime checkpoint: `c899c70d205b9c88cdd0314ef99f580c218e6a5f`; tree `6e53d2ca3f31409ab772907dafde0354fd22406d`. Main baseline: `ec727f3c1d4cd9cc29ce131350d061afa7531460`.

- Work content now precedes inspection utilities. Supplied title/state, intent and blockers lead; full facts and relationships remain present. Source/browser metadata is in a native disclosure. Why/Relations investigation behavior remains available.
- Embedded Work has one selected-detail CLI control and one workspace dashboard-link control. Direct record links retain their own copying. Results-row and relation-specific copying are distinct targets/contexts and remain available.
- Inspect children reveals Results and focuses its heading below the sticky header while retaining the selected parent. Loaded-page/filter absence is labeled separately from unavailable detail.
- `work_pane=results|detail` is an allowlisted presentation parameter. Copy/reload preserves the phone pane; selecting a Work reference returns to Detail. Invalid pane values reject before dependent reads. Legacy links without it retain behavior; it never enters accepted API queries.
- Other DetailView/RecordInspection hosts retain the default variant. No schema, accepted types, lockfile, dependencies, pagination/virtualization, graph semantics or polling cadence changed.

The review's proposed three detail tabs are not implemented in this checkpoint. This smaller reorder/disclosure removes the largest measured obstruction without reorganizing every section. Secondary filter disclosure and further detail organization remain separate planned checkpoints.

## Visible task verification

Using the committed service-worker-free HTTP build and product controls in the Codex in-app browser:

1. Phone 390×844: opened F1/T-0003, identified supplied title and BLOCKED state, read intent and blocked_by, opened Source and browser metadata and confirmed their separate labels.
2. Followed parent S-0001, then Inspect children. Results appeared immediately with parent filter S-0001, selected parent preserved, and results heading focused. The absence of the parent from its own direct-child results is explicitly explained.
3. Desktop 1440×1000: inspected the same record and existing facts/related records. Narrow 720×500 light layout and phone dark layout checked; appearance restored to System and temporary viewport overrides reset.
4. Automated compiled W02 regression covers both desktop and phone child navigation, result-heading focus, copied/reloaded Results pane, selecting a result into Detail, copying ownership, provenance disclosure and API query isolation.

Phone dark measurement repeats the baseline's F1/T-0003 fixture and viewport:

| Measure (CSS px) | Frozen W06 baseline | Checkpoint 1 |
|---|---:|---:|
| Ticket title document Y | 1090 | 439 |
| Blocker heading document Y | 1422 | 771 |
| Document height, provenance closed | 2564 | 2012 |

Light and dark checks produced the same new title/blocker positions. These are document coordinates, not timing targets, physical-device testing or an assertion that every ticket fits one viewport. The supplied summary and full projection facts still consume legitimate space. `measurements.json` records the method.

Browser evidence includes original JPEGs and compiled W02 screenshots in `web/docs/reviews/work-density-checkpoint-1/`. Full-page captures may show sticky chrome at the current scroll position. The 720px check is narrow reflow; actual browser 200% zoom is not claimed by this implementer pass and remains a reviewer check.

## Verification and source freeze

The source was committed before the offline build. A clean detached shared clone built with pinned Node v22.22.2/npm 10.9.7 and immutable builder `sha256:ef83c04ea3f483d4a9c2a945f4669786018fa6ce31757c7f938c930cc2db8407`, network disabled. The offline gate checks accepted generated types, all contract artifacts, typecheck, lint, 167 tests in 19 files, both builds and production exclusion.

Commands: `freeze-w06-evidence.sh c899c70d205b9c88cdd0314ef99f580c218e6a5f` with the established pinned Node/Chromium/builder/W05 baseline variables; strict premium `audit_project.py <frozen web> --mode strict --no-write`. The existing freeze procedure runs W01–W06 plus HTTP demo regressions and verifies clean source/build manifests afterward. Its recorder measurement is an inherited procedure check, not a Work performance comparison.

The initial source `8510c7b` failed the offline typecheck because two new test role queries used Playwright's `exact` option rather than Testing Library's options. `c899c70` corrects those test types and formatting. Only the corrected clean build is used for this packet; no prior working-tree screenshots are attributed to it.

Final verification: offline gate **PASS** (167 tests, 19 files); W01–W06 and service-worker-free HTTP demo **PASS**. Compiled W02 includes the new desktop/phone Work check; W06 includes 22 groups. Source remained clean and both complete build manifests were unchanged after verification. Production build-manifest SHA-256: `4821bab12dfc58be2a035bb78c96fff2e394588b581319af6dd719dec4e8b02b`; demo: `2533807f6f8320dd7c4f3c1a20853a96b46603de00c8bc0f0d286c0acb6f5cd0`. These identify complete manifest files, not one bundle.

Runtime identities, build hashes, complete manifests, suite outputs and screenshot hashes are recorded alongside this packet. Strict premium audit: exit 0; no findings. Static audit does not establish usability or independent acceptance. CI on the published branch is a separate gate; no green-CI claim is made by these local results.

## Independent reviewer tasks (pending)

On desktop and phone, use only the product UI:

- Find T-0003 and its supplied blocker, then open Why state. Confirm record-level reasons/blocked_by have not become an inferred status explanation.
- Follow S-0001 and Inspect children; confirm Results is visible, focus is below the header, parent selection survives and the note explains its absence from child results. Select a child, return to Results, copy/reload and test browser Back.
- Inspect all projection facts and disclosed source/browser metadata. Confirm currentness/refusal/refresh-failure warnings remain visible independently of disclosure and no fields have disappeared.
- Test direct `/work/T-0003` copying and legacy selection links; compare unaffected Runs/Evidence detail layouts and shared Why/Relations overlays.
- Exercise light/dark, long/unknown/archived/empty/error states, keyboard, narrow phone and actual 200% zoom. Confirm concealed detail reads stop and Result/Detail switching retains accepted revalidation behavior.

Record steps, IDs, findings and disposition. Implementer checks and green CI do not substitute for this review. All future API and Knowledge design changes remain outside this improvement.

## Independent review received

The supplied main-line review is preserved in `web/docs/reviews/work-density-checkpoint-1-independent-review.md`: **CHANGES REQUESTED**, confined to phone Results → Detail focus/scroll (F1) and off-screen Results focus after browser Back (F2). Its independent pinned rebuild passed and matched the original build byte for byte. All other covered reviewer tasks held; its listed coverage limits remain explicit. Corrections and their exact-source verification are recorded separately; independent re-review remains pending.
