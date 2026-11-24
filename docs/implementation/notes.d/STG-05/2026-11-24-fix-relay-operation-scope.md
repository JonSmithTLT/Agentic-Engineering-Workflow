**The provider relay's operation scope (2026-11-24): the relay forwards only the provider operations its policy
allows.** Every relay (API key, stored login, and a client certificate alone) checks each request before its
credential is resolved and before anything is connected:
- **The path** must lie under the upstream's prefix, spelled unambiguously: no empty, `.` or `..` segment, no percent
  escape, no fragment (`:` is allowed on an API-key relay, for Google's model calls). Otherwise it is refused 403,
  `outside_upstream_path`, the stored-login relay's reason.
- **The operation** must be a model call or the model list (`relay.DEFAULT_OPERATIONS`), or one the operator's adopted
  execution policy names for the provider in `containment.network.relay_operations.<provider>`, as `METHOD /path` with
  the path exact under the upstream (legality-affecting, read on the host at the relay's start). Otherwise it is
  refused 403, `operation_not_permitted`.

A refusal is counted and recorded like any other (outcome `refused`, its reason, transport `not_established`), names
where the operator allows an operation, and sends nothing upstream. A policy-listed request is recorded with operation
`policy_listed`. The launch self-test's own relay lists its check path, which no run's relay forwards. A policy entry
the relay cannot match exactly refuses the run's start (`CONTAINMENT_UNAVAILABLE`, reason `bad_relay_operation`).

The default set comes from `tests/fixtures/opencode/relay-operations-2.2.6.json`, the calls OpenCode 2.2.6 makes
through the relay. They were derived from the repository's existing evidence (the usage fixtures' live turns, and the
paths the plan-login qualification records), not measured in a fresh session: the pinned binary could not be
installed where this was built. A live session that records its relay paths should confirm the fixture.
