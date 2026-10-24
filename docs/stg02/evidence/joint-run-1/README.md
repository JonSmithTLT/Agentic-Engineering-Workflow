# Joint run 1 evidence

Runtime: website `af77308aa48cbc73a73791b58b807c0a9ebdbe55`, reviewed wrapper `f8dd097cf9f929c1759820b66b4f169cb32fad11`, backend `7acb60f5cf9c8f74285e3ee4533ab24f8dc12160`. Synthetic `joint-state-1`; no real credentials/project. See `../../JOINT-TEST-NOTES.md` for method, operator-relayed setup, classifications and limits.

`traffic.json` records primary browser HTTP responses, exact command bytes, wire headers and body SHA-256. `session.json` records captures/UTC/POST counts. Separate diagnostic JSON files distinguish literal-path HTTP checks from product navigation. `lost-*.json` records the actual held response and identical reconciliation. `SHA256SUMS.txt` inventories this selected bundle; full original drivers and launcher failures remain in ignored local artifacts.

Both `1440-` and `390-` images are responsive captures, not separate participants or physical devices. Capture labels are not assertions that a step passed:

- `05-owner` is the real encoded-path 404, not a successful owner read.
- Initial `05-owner-index` was overwritten by withdrawal. The original positive index is visible in `06-protected`; original HTTP seq7 remains intact. The duplicated negative index images are not presented as original positive evidence.
- `probe-outage-work-503` was captured before refresh settled and still shows the prior partial body. It is **inconclusive** about the completed 503 view. Run 2 repeats this with corrected capture waits.
- Lost-response timeout happened before stopping the wrapper. Exact reconciliation worked, but run 1 does not verify stop-before-timeout fault ordering.

No independent joint acceptance, remote CI, human usability, source qualification or production-adoption claim.
