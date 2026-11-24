**The provider relay's operation scope (2026-11-24): the relay forwards only the provider operations its policy
allows.** Every relay (API key, stored login, and a client certificate alone) checks each request before its
credential is resolved and before anything is connected:
- **The path** must lie under the upstream's prefix, spelled unambiguously: no empty, `.` or `..` segment, no percent
  escape, no fragment (`:` is allowed on an API-key relay, for Google's model calls). Otherwise it is refused 403,
  `outside_upstream_path`, the stored-login relay's reason.
- **The operation** must be a model call or the model list (`relay.DEFAULT_OPERATIONS`), or one the operator's adopted
  execution policy names for the provider in `containment.network.relay_operations.<provider>`, as `METHOD /path` with
  the path exact under the upstream (legality-affecting, read on the host at the relay's start). An entry applies to
  whichever upstream the provider's relay uses, its API key's or its stored login's; one with `:` refuses a
  stored-login relay's start, as no path there holds one. Otherwise it is refused 403, `operation_not_permitted`,
  and its record names the request's method and its endpoint under the prefix (no query), which is what the operator
  would list.

A refusal is counted and recorded like any other (outcome `refused`, its reason, transport `not_established`), names
where the operator allows an operation, and sends nothing upstream. A policy-listed request is recorded with operation
`policy_listed`. The launch self-test's own relay lists its check path, which no run's relay forwards. A policy entry
the relay cannot match exactly refuses the run's start (`CONTAINMENT_UNAVAILABLE`, reason `bad_relay_operation`).

The default set comes from `tests/fixtures/opencode/relay-operations-2.2.6.json`, the calls OpenCode 2.2.6 makes
through the relay. They were derived from the repository's existing evidence (the usage fixtures' live turns, the
paths the plan-login qualification records, and the 2026-10-25 measurement of the Anthropic and Google routes on
2.0.18), not measured in a session of the pinned version: the pinned binary could not be installed where this was
built.

Known limits, each with its owner:
- **The scope is the method and the path alone; request bodies are not inspected.** What a model call's body may ask
  of the provider is scope this row decides (the designer's), not this change.
- **Live confirmation of the default set** is a follow-on of this series: the next relay pull request (the relay's
  bounds and outcome) adds to the live lane (`tests/live/test_opencode_live.py`) a check that a real session at the
  pinned OpenCode has every relayed request's `operation` in the default set and none refused for scope.
