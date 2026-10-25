**STG-05 CS-4 (2026-10-25): the Lead contained.** On Linux, `aew opencode` runs the Lead's OpenCode TUI in a
self-tested `lead` sandbox, on a network of its own, on a terminal AEW relays, and the session still works as the
operator's own did. ADR-0009's amendment of 2026-10-25 says how; the designer's CS-4 hand-off and its addendum 1 are
the source.

- **The sandbox (R-2):** role `lead`, mode `required` unless the policy says `allow_weaker` (then labelled
  `workdir_separation_only`, with the reason, and the start line says so). The working tree is writable; `.aew` and
  the git metadata are read-only; `.aew/local` is masked except the session's run directory and the Lead's own
  OpenCode state (`.aew/local/harness/lead`, per project); the operator's OpenCode configuration and login are masked
  wherever their variables put them. Rows 1 to 6 of the self-test run first, row 4 in the Lead's form.
- **The CLI inside** is a non-writer (`aew (contained Lead)`): reads are lock-free, Lead commands go through the
  broker, and a write meeting the read-only store is refused (`PERMISSION_DENIED`, reason `lead_contained`).
- **The network:** `proxy_only` with any-public egress (`HTTPS_PROXY` and `HTTP_PROXY`, loopback excepted); one
  relay per provider of the operator's stored login whose key comes from a known variable (openai, anthropic,
  google), each provider's `baseURL` at its relay, its variable a sentinel inside. The stored login is read on the
  host in memory only (SQLite read-only mode, busy timeout). `--provider-env NAME` feeds that provider's relay, never
  the Lead's shell. opencode's own key is not relayed (its models carry their own catalog address), and the start
  line says so; its free models still work through the egress proxy. A plain `http://` request is told its
  `https://` form.
- **The terminal relay (R-7):** a pseudo-terminal between the operator's terminal and the TUI, bytes unfiltered, the
  window size followed, and the terminal given back (the TUI's own exit sequence and the saved settings) on every
  ending, the broker's and the reaper's deaths included.
- **Messages:** the start lines (each login and whether it is relayed, what `--provider-env` feeds, the MCP servers
  left out, by name); one line in the Lead's system text from its label; a sandbox that cannot start for want of a
  user namespace names `user.max_user_namespaces` and the fix (ST-27 fact 5).
- **ST-38 (the server password), accepted** by the designer's ruling: the residual test now asserts the sentinel and
  the password and never the key, for a worker's run and the Lead's session, and three tests pin the ruling's
  conditions (the password new per launch and in no file outside its run; no context reaching another run's server;
  no route-closing control a harness permission rule).
- **Follow-on, measured:** a stored opencode key is not relayed (see above); serving it needs a per-model `baseURL`
  for every opencode catalog model, which the session cannot list before the TUI starts.
