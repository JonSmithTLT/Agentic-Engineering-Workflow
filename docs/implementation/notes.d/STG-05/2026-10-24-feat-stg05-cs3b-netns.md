**STG-05 CS-3b (2026-10-24): a worker run's own network, the shim and the provider relay.** CS-3's second pull
request wires in CS-3a's egress proxy and builds the rest of F28 for workers on Linux. ADR-0009's amendment of
2026-10-24 says how; F28's design gains a dated §7 (the egress policies, ruling R-6, where the relay puts the
credential).

- **The mode:** `containment.network.mode` in the execution policy, else `proxy_only` on Linux. `isolated` has no
  route out, `shared` is the host's network (labelled so), and Windows stays `not_provided`. A private mode gets a
  network namespace of its own (`--unshare-net`).
- **The routes out of `proxy_only`:** the provider relay, which holds the provider's key (a sentinel stands in for it
  inside), connects only to the policy's fixed upstream (`containment.network.upstreams.<provider>`, or a known
  one), and streams the answer back; and CS-3a's egress proxy, when the allowlist names something (the policy's
  `egress_allow` and the harness's own needs: OpenCode's catalog, `models.opencode.ai:443`). An in-sandbox shim, the
  harness's parent, forwards loopback ports to them, and the harness server's port to the supervisor.
- **The label's `network`** is now an object: the mode, the relay and its upstream, the allowlist, R-6's stated
  residual, and, at the run's end, what the relay and the proxy decided, counted.
- **Checks** run `isolated` unless they ask for `shared` from a `shared` run, and their evidence records which.
  `proxy_only` for a check is not built.
- **The launch self-test's row 1** proves outcome 4 on the real sandbox (a namespace not the launcher's, no host
  abstract socket or loopback port inside, only the shim's ports listening) and the paths through the shim, the relay
  and the egress proxy; it fails closed under `required`. Row 2 fails on a host abstract socket listed inside a
  private network.
- **The live lane** (F28's NET-19 and decision 6) passed on the Rocky VM on 2026-10-24: OpenCode 2.0.18 on
  `openai/gpt-5.6-luna#medium` with a real key the supervisor held. Implementer, reviewer and verifier ran
  `proxy_only` and ended with evidence, and 14 streamed model requests crossed the relay. Against the real upstream, a
  slow client got its stream whole, and an interrupted turn closed the upstream at once. No file the lane left held the
  key. ADR-0009's amendment has the numbers, and two limits it showed: the relay's `cancelled` count also counts
  complete answers, and OpenCode's glob and grep tools need ripgrep on the host, since a contained run cannot
  download it.
- **Not yet:** the Lead's harness on `proxy_only` with the any-public egress policy is CS-4's, and F28's row stays
  open until then.
