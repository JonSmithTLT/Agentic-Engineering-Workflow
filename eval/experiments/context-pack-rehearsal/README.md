# Implementer context-pack rehearsal

REPORT-1 qualifies F19's delivery and grading interfaces on one public synthetic ticket. The three scripted workers make the same empty edit. The preregistered budget is zero. No model runs, so these scores carry no information about whether context improves a worker's performance.

The integration test builds the five-file fixture with F19, makes an AEW ticket, accepts a plan that points to three source documents and assigns an implementer. The generated B pack is regenerated from the dispatch records and compared byte for byte. A keeps the ticket, role, reporting format, guardrails, authority and checks. Its header lists the sections actually present. C adds independently checked source notes to A. Every variant retains the same preamble, snapshot, capabilities, required output and source revision. The experiment permits 32,000 characters per pack. The normal B dispatch had no truncations.

| Fact in the shared checkout | A | B | C |
| --- | --- | --- | --- |
| JSON needs a status | Ticket | Ticket | Ticket |
| Pending means `queued`, superseding `waiting` | Discoverable | Current document pointer in accepted plan | Both spellings, explicit precedence and both citations |
| Completed rows use `done` | Discoverable | Current document pointer | Fact and citation |
| Missing phase means `unknown` | Discoverable | Legacy document pointer | Fact and citation |
| CSV preserves the original UTF-8 bytes | Discoverable | CSV document pointer | Fact, compatibility details and citation |

Each cell registers before the adapter sends its initial prompt. Each fresh test-owned OpenCode V2 server records the message over loopback. The test reads back the session's user message and compares the full UTF-8 input with the frozen hash. It checks every starting file, the empty session history, the identical Git revision and the final export hashes. The logical workspace named in the original dispatch remains in every prompt. Each synthetic session runs in its own F19 copy of that tree. Only the scripted no-edit operation runs there. This qualifies the adapter message boundary. An actual model host still requires the F19 arm-host/evaluator split.

The example directory holds one run's frozen plan, attempt manifest, dispatch source manifest and exact B pack. Session IDs, freeze time and absolute workspace paths belong to that run. Fresh runs pin their own generated prompt hashes before their first attempt. The test stores exact received inputs under `cells/{a,b,c}/received.md` in its scratch directory. F19 records attempts under `ledger/`. On the scoring pass it records the exported trees' scores separately in `ledger/scores.jsonl`. The unmodified exporter should fail the three JSON criteria and pass CSV in every arm.

## Reproduce

Use the repository test environment and a fresh scratch directory outside Git trees.

```sh
python -m pytest -q tests/integration/test_eval_context_pack_rehearsal.py
python -B eval/experiments/context-pack-rehearsal/evaluator/calibrate.py
```

The integration tests exercise the product scorer on the frozen exports and independently re-run the five known-answer controls. Normal Linux scoring requires usable bubblewrap namespaces and a writable weaker-context register. The standalone calibration drives the same checks on only its built-in trusted scripts and records that its execution is uncontained. The case manifest releases only `fixture/` to each worker. The evaluator owns four grading criteria, the sample vectors, criterion-to-source map, expected verdicts and control edits. This public synthetic example is unsuitable for held-out inference. The wider F19 hold and historical experiment pins continue to apply.
