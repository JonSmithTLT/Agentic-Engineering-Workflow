## Report source notes

- The current decision in `docs/status-current.md` maps pending input to JSON status `queued` and done input to `done`. It supersedes the earlier `waiting` spelling in `docs/status-retired.md`.
- `docs/legacy.md` records the original row contract. A missing phase has JSON status `unknown`.
- `docs/csv.md` defines the existing UTF-8 CSV bytes, including the id,title header, input row order, doubled quotes and CRLF through the final record. Keep the status addition in JSON.
