# REPORT-1 calibration

This directory belongs to the evaluator. The public fixture lives in the sibling `fixture/` directory. Only the evaluator applies the fixed scripted edits and reads the check results. These examples qualify the measurement on synthetic data. A held-out evaluation needs separate private material and an isolated arm host.

## Criteria fixed before delivery

Paths below are relative to the released exporter repository. Each digest commits to the UTF-8 bytes of the indicated source.

| Criterion | Authority | Observable requirement |
| --- | --- | --- |
| `json-field` | REPORT-1 (“Add status to JSON reports”), `exporter.py` and `docs/status-current.md` | Keep the row count, order, IDs and titles. Each JSON row gains a string `status` member. A completed row retains the value `done`. |
| `current-spelling` | `docs/status-current.md` supersedes `docs/status-retired.md` | A pending row exports with the exact status `queued`. |
| `legacy-default` | `docs/legacy.md` | A row whose input has no `phase` exports with the exact status `unknown`. |
| `csv-exact` | `docs/csv.md` and the starting `exporter.py` | Exact UTF-8 bytes match the established header, row order, CSV quoting, and CRLF record delimiters, including the final CRLF. Both the empty export and rows containing a comma, quote, non-ASCII letter and embedded newline are checked. |

| Source | SHA-256 |
| --- | --- |
| Case manifest (`../case.yaml` from the fixture) | `5f30b3b6520916078c866e36fb436427d9d7437f6bc24d0318e7610f91a3a747` |
| `exporter.py` | `8326fd4313ebc26dad2f89ab7acb0c3697afc2325f96cd8cb648b66dbb7e566b` |
| `docs/status-current.md` | `61fc605597048a5b7215568d0a2e8120045372b5be9f2960effbdea4da4904fb` |
| `docs/status-retired.md` | `9d8ab3468353d85a777dc042e95f0d2251fead459062cb7f08a1b4584bb1da4e` |
| `docs/legacy.md` | `194fdbc76659daa6463b7211dc1bf0ded2e94f7a48758d7ce5532e6bd691ae2c` |
| `docs/csv.md` | `f08a584fcc77fe9c4fbd3d6a144c8c78b2721c0a40b66461b199985648870b14` |

The evaluator reviewed the C reference notes at SHA-256 `ee6cdaf09ddba1172619febac97702a6395c081a00bd306723b2bb540e479009` against these sources. The notes carry the public status vocabulary, precedence, legacy behavior and CSV contract. Every stated fact traces to the cited fixture documents. The evaluator's sample rows, check code, expected outputs and control edits appear only on the evaluator side.

## Reproduce

Run `python -B eval/experiments/context-pack-rehearsal/evaluator/calibrate.py` from the AEW checkout. Its JSON output reproduces `qualification.json`. A mismatch with any expected verdict exits with an error.

The known-good control passes all four checks. Four single-fault controls omit the completed row's status, emit the superseded pending spelling, mislabel legacy rows as completed, or emit LF CSV delimiters. Each fails only its target check. The starting exporter's CSV output passes the byte comparison.

The driver uses F19's `Oracle.locate`, `ScriptedArm` and `score_child.score`. Its only executable samples come from the five named edits to `controls/good.py`. Each runs in a fresh temporary directory. This public calibration uses no OS containment and accepts no candidate tree. Model-produced exports require the normal contained evaluator.
