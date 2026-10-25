**An input for this group's matching** (map v1.20 §7, item 3.4), from the designer's rulings of 2026-10-25 on the
Lead's friction log, batch 7 (B7-1, B7-3, B7-5, B7-8). Nothing in batch 7 is built before V-01 (B7-S).

- **The flake record is shown here** (B7-1). A-07 owns the record (HOLD-07).
- **Admission control is an advisory projection field** (B7-3: R-01's advice, R01-01), owned by A-15 (HOLD-15).
  - **It shows:** open changes, rounds per change, the CI queue, and plans ahead of build capacity, with merges per
    hour from A-15's records (W16).
  - **It advises** against new build work above a threshold. The threshold is the operator's setting, and the product
    ships no default. Fixes for a red `main` are exempt, and nothing is gated by it.
- **Printed commands** (B7-5): an operator-facing command that AEW prints is checked on its target, as printed. One
  that runs under sudo names its absolute path. These are A-10's executable actions.
