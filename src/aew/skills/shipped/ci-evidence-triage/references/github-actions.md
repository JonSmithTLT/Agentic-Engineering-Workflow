# GitHub Actions: exact attempts

Use only for GitHub Actions. Commands are read-only examples; substitute observed IDs and the actual repository. Verify installed CLI support. Do not infer identity from a workflow title.

```text
gh run view RUN_ID --repo OWNER/REPO --attempt N --json databaseId,headSha,event,attempt,status,conclusion,url,jobs
gh api --paginate repos/OWNER/REPO/actions/runs/RUN_ID/attempts/N/jobs
gh run view RUN_ID --repo OWNER/REPO --attempt N --job JOB_ID --log
```

Bind JOB_ID to the jobs returned for that attempt before reading it. Paginate jobs/runs; a truncated page is not a full matrix. Record workflow, runner/matrix and step conclusions, including cancelled and skipped checks. Inspect event/checkout behavior: pull-request workflows can test a generated merge while other events test different refs. Do not assume all providers or events test merges.

Whole-run `--log-failed` can be unavailable while the run is incomplete. Try a completed job's log when available, or report pending retrieval with a bounded wait; log availability varies by lifecycle, permissions and retention. Empty output never establishes success. A run marked complete may still have expired logs.

Attempt archive endpoint: `GET /repos/{owner}/{repo}/actions/runs/{run_id}/attempts/{attempt_number}/logs`. It returns a redirect, not JSON log content. Use a permitted client that handles it and archive bytes correctly; retain only appropriate evidence, never credentials or temporary signed download URLs. Keep retrieval errors separate from the run's actual outcome.

A rerun retains the original event SHA/ref, so rerunning an old run does not test a new push. A latest attempt can include a subset of rerun jobs; account for the provider's retained job/check provenance instead of combining unnamed successes across attempts. Never launch a rerun merely to collect read-only evidence.
