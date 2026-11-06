**The three pieces #338 left for after #330 (2026-11-06):** the pull request on branch `feat/relay-route-label` builds them.
- **One allowlist.** The supervisor builds the run's egress allowlist once and gives the same one to the self-test and to the run's egress proxy (`RunNetwork.start(allow=...)`); the network no longer builds its own from the policy.
- **Row 1 records the list.** The self-test's row 1 records the allowlist it checked (`egress_allow`).
- **The check is shown, and the refusal's reason is carried.**
  - The relay-route check of the pinned model's family (`matches` or `unverified`) is on the run's network label and in the launch's output beside its status, carried by the supervisor's "started" acknowledgement.
  - An adapter's refusal reason (`relay_family_mismatch` among them) is on the run's record and in the launcher's error, carried by the failure acknowledgement.
  - Both are closed sets owned by `aew.harness.base`; the launcher passes on nothing else.
