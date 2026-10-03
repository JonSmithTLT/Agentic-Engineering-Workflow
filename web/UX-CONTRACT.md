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

Select opens in place and preserves results; close returns focus to entry or heading. Filter/page changes preserve explicit selection with an out-of-results notice; filter change resets cursor. Stream/table toggles keep cursor/selection. Native selects use their supplied option identities. Tabs implement arrow/Home/End navigation. Narrow pane switches stop concealed detail polling and revalidate when revealed. Metadata and graph disclosures are non-modal.

Initial reads show loading or an inline error/retry. Background failure retains marked valid data. 401/403 clears inaccessible data and validator. Session/case changes retire responses, caches and graph state. Empty/no-results explain recovery. Unknown values retain raw warnings. Missing explanation does not derive meaning from neighboring fields.

No edit/create/delete, credential handling, billing, legal workflow or data-entry form is introduced by W03. Toast/dialog/date/form capabilities are not applicable. Future capabilities require explicit ownership rather than screen-local substitutes.
