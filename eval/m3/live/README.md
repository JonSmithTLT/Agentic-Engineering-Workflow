# M3 live model trials (step 8)

`model-trials.jsonl`: one record (`aew/live-model-trial/v1`) per trial of `tests/live/test_opencode_model_live.py`, all on 2026-09-28 with OpenCode 2.0.18 and free models. Summarized in `docs/implementation/harness-conformance.md` §6.

- `scenario`: `lifecycle` (implementer, reviewer, verifier) or `rework` (a seeded defect, then real models; §6.2).
- `series`: when and as part of what the trial ran. The clean specimen is the whole live lane run with the checkout otherwise untouched.
- `aew_fixed`: the step-8 defects (M3-D2..D7) whose fixes were in the code the trial ran on. Trials that found a defect ran without its fix; `note` says which.
- `routing`: per-role models, if any (the asymmetry trials); otherwise every role used `model`.

Each record holds:
- the model, the agent's shell, the step limit and the deadline;
- per role run (implementer, then reviewer, then verifier, as far as the model got): status and reason, wall time, `model_check` and the effective model, steps, `tools_called` (names and counts only), tokens and cost, first-step input tokens, context sizes, permission requests rejected, forms cancelled, `bridge` requests with `outcomes` by operation and error code, the evidence recorded (ids, kinds, results), and the workspace's changed paths;
- the Lead's steps and their outcomes, the final state, an independent hidden test of the implementation, and whether its changes stayed in scope;
- for `rework`: each implementation attempt (seeded or model, correct or not, its snapshot fingerprint, any relaunch), each review (disposition, findings, resolved findings, ingest outcome), each verification (claims), the probes (the rejected implementer's credential, re-ingesting the stale review), the state history, every invocation with its runs and credential ids, and the gates with the evidence bound to them at the end;
- the project's control-state `footprint` at the end (`tools/perf/control_plane.py footprint`).

No transcript, prompt, tool input or report text is kept here: those live only in each run's private OpenCode state, which the test leaves in its temporary directory.

Reproduce: `AEW_LIVE_RESULTS=model-trials.jsonl AEW_LIVE_MODEL_TRIALS=3 pytest --live tests/live/test_opencode_model_live.py -p no:xdist -q`. Add `env -u SHELL` for PowerShell as the agent's shell, and `AEW_LIVE_ROUTING=implementer=opencode/mimo-v2.6-flash-free,reviewer=opencode/space-bunny-free#high,verifier=opencode/space-bunny-free#high` for the asymmetry trials.
