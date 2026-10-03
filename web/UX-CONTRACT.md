# AEW frontend behavior contract

Sources: `docs/design-direction.md`, `docs/design/plans/w02-workspace.md`, `docs/design/plans/w03-journal.md`, and accepted API referenced by `docs/c0-approval.json`. Backend owns workflow/authorization/health and persistence. No mutating product actions.

## Canonical UI map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Table Selection | InvestigationWorkspace + entity links | W02/W03 plans | results/detail, journal Stream/Detail | W02/W03 component/browser tests |
| Select/Listbox | native select with shared styles | DESIGN.md | native OS popup | keyboard/open-popup browser checks |
| Scrollbar | src/styles.css document baseline | DESIGN.md | table/graph geometry only | phone overflow + computed-style check |
| Navigation | api/navigation + React Router | W02/W03 plans | accepted entity, demo journal reference | copy/reload/back + contract guards |
| Safe content | SafeContent | accepted display contract | plain/Markdown | hostile-content/CSP checks |
| Provenance | SourceStrip + RelationsExplorer | W02/W03 plans | accepted default, journal reader adapter | source/bounds/unknown checks |

## Journal interaction/state ledger

Select opens in place and preserves results; close returns focus to entry or heading. Selected ID stays visible above both panes; mobile Results/Detail buttons show the current pressed state. Following a Journal reference focuses its ID/title heading below the sticky header. Filter/page changes preserve explicit selection with an out-of-results notice; filter change resets cursor. Stream/table toggles keep cursor/selection. Native selects use their supplied option identities. Tabs implement arrow/Home/End navigation. Narrow pane switches stop concealed detail polling and revalidate when revealed. Metadata, type legend and graph disclosures are non-modal. Loadable graph nodes are marked not expanded until loaded; unavailable references stay terminal.

Initial reads show loading or an inline error/retry. Background failure retains marked valid data. 401/403 clears inaccessible data and validator. Session/case changes retire responses, caches and graph state. Empty/no-results explain recovery. Unknown values retain raw warnings. Missing explanation does not derive meaning from neighboring fields.

Desktop selection from a Journal results link preserves focus on that link and its sequential Tab position; the selected-ID status announces selection politely. Phone results selection focuses the replacing detail. Navigation originating inside detail, graph references or initial deep links focuses the available ID/title heading. The origin is captured before the asynchronous read, so refreshes do not move focus.

No edit/create/delete, credential handling, billing, legal workflow or data-entry form is introduced by W03. Toast/dialog/date/form capabilities are not applicable. Future capabilities require explicit ownership rather than screen-local substitutes.

## Comparison and packet interaction/state ledger

W04 source choice is explicit; accepted invocation identity may seed A but never chooses a snapshot or counterpart by similarity/time/success. Changing one side preserves the other; Swap exchanges both source and run choices. Below1024px paired values stack A/B per field. Missing or partial data is Unavailable, never Same/Different. Structural differences are presentation only.

`InvestigationTabs` owns W04 keyboard tab behavior; native selects and `Pager` retain their existing owners. `focusBelowHeader` owns W04 heading focus. Packet models, receipts, bindings and `PacketInspector` are independent of comparison; future Journal/retrieval consumers may reuse them without inferred semantic relations. SourceStrip's optional readSnapshot identifies the actual preview reader without changing accepted provenance.

Opening a packet replaces comparison and stops hidden intervals. Back restores comparison state/scroll/origin focus after the route commits; direct inspector reload resolves only its owning source. Current visible sources poll10seconds; fixed sources and packet pages have no intervals. Refusal clears all representations/queries owned by the affected preview reader, preserving the other side and accepted scopes. Validation occurs before payload caching, including identity/snapshot and packet/receipt bindings. Ordinary failures retain marked valid prior data. No raw prompt/credential/artifact bodies or inferred receipt claims.

Copy links allowlist explicit source/run/tab/filter/packet/page/case presentation state. Opaque demo cursors are filter/dataset/project/revision-bound and reloadable, not authorization credentials. Unsupported historical links stop preview reads. Source chooser payloads contain metadata only, so denied details cannot leak through collection payloads. Budget values and selection explanations are supplied; the browser never fabricates token accounting or selection reasons.
