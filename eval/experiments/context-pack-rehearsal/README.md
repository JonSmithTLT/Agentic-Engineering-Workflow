# Implementer context-pack rehearsal

REPORT-1 qualifies F19's delivery and grading interfaces on one public synthetic ticket. Each scripted worker appends the same harmless comment to the exporter. The preregistered budget is zero. No model runs, so these scores carry no information about whether context improves a worker's performance.

The integration test builds the five-file fixture with F19, makes an AEW ticket, accepts a plan that points to three source documents and assigns an implementer. The generated B pack is regenerated from the dispatch records and compared byte for byte. A keeps the ticket, role, reporting format, guardrails, authority and checks. Its header lists the sections actually present. C adds independently checked source notes to A. Every variant retains the same preamble, snapshot, capabilities, required output and source revision. The experiment permits 32,000 characters per pack. The normal B dispatch had no truncations.

| Fact in the shared checkout | A | B | C |
| --- | --- | --- | --- |
| JSON needs a status | Ticket | Ticket | Ticket |
| Pending means `queued`, superseding `waiting` | Discoverable | Current document pointer in accepted plan | Both spellings, explicit precedence and both citations |
| Completed rows use `done` | Discoverable | Current document pointer | Fact and citation |
| Missing phase means `unknown` | Discoverable | Legacy document pointer | Fact and citation |
| CSV preserves the original UTF-8 bytes | Discoverable | CSV document pointer | Fact, compatibility details and citation |

Each cell registers before the adapter sends its initial prompt. The normal OpenCode adapter launches a fresh test-owned V2 server, projects its implementer agent, opens the session and sends the initial prompt. The test reads back the applied agent, system text, permissions, synthetic model reference and user message over loopback. It compares projection, skills, permissions and prompt hashes. Each cell's fresh F19 checkout occupies the exact path named by the original dispatch for that turn. The fake tool writes through the absolute path in that workspace. F19 verifies the resulting file and archives the run before another cell starts.

The portable delivery pass uses fixed trusted scripts. The Linux deferred-scoring pass also encloses each fake server and all its tools in F19's bubblewrap layout. Its view exposes the current workspace, private run directory and a staged copy of the public fake-server dependencies. The coordinator's directory and source checkout, including Git object stores, are masked. The fake worker attempts reads of the check file, frozen plan, current pack, ledger and existing prior receipts. The parent verifies each file exists. Every read must be refused, while the workspace edit must succeed. Windows runs the portable path. A held-out evaluation still needs the F19 arm-host/evaluator split.

The example directory holds one run's frozen plan, attempt manifest, dispatch source manifest, exact B pack and three deferred score records from the isolated Linux pass. Session IDs, freeze time and absolute workspace paths belong to that run. Fresh runs pin their own generated prompt hashes before their first attempt. The test stores exact received inputs under `cells/{a,b,c}/received.md` in its scratch directory. F19 records attempts under `ledger/`. On the scoring pass it records the exported trees' scores separately in `ledger/scores.jsonl`. The harmless comment preserves the exporter's behavior. It should fail the three JSON criteria and pass CSV in every arm.

## Reproduce

Use the repository test environment and a fresh scratch directory outside Git trees.

```sh
python -m pytest -q tests/integration/test_eval_context_pack_rehearsal.py
python -B eval/experiments/context-pack-rehearsal/evaluator/calibrate.py
```

The integration tests exercise the product scorer on the frozen exports and independently re-run the six known-answer controls. Normal Linux scoring requires usable bubblewrap namespaces and a writable weaker-context register. The standalone calibration drives the same checks on only its built-in trusted scripts and records that its execution is uncontained. The case manifest releases only `fixture/` to each worker. The evaluator owns four grading criteria, the sample vectors, criterion-to-source map, expected verdicts and control edits. This public synthetic example is unsuitable for held-out inference. Each single-fault patch fails its intended criterion. The mixed-batch patch applies the last row's phase to the full batch and fails both pending and legacy criteria. The wider F19 hold and historical experiment pins continue to apply.
