**STG-05 CS-4 (2026-10-25): the Lead contained.** On Linux, `aew opencode` runs the Lead's OpenCode TUI in a
self-tested `lead` sandbox, on a network of its own, on a terminal AEW relays, and the session still works as the
operator's own did. ADR-0009's amendment of 2026-10-25 says how; the designer's CS-4 hand-off and its addenda 1 to 3
are the source.

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
  the Lead's shell. opencode's own key is not served yet (addendum 2, ruling 2: its models carry their own catalog
  address). It fails closed: the key never goes inside, OpenCode then offers only the free opencode models, which
  work through the egress proxy, and the start line says so. A plain `http://` request is told its `https://` form.
- **The ChatGPT login (addendum 1, option a):** relayed as stored, to its own upstream. The relay re-reads the
  operator's login store on each request, read-only, so a refresh by the operator's own OpenCode is used at once; AEW
  never refreshes or writes it. An expired one is answered with a message naming `opencode auth list` and saying the
  next request then works, with no restart. Inside, the Lead's own login store holds a row with the relay's sentinel.
- **The login's expiry and its shape (addendum 2, ruling 1):** the operator's token lasts about 240 h, so option (a)
  stands. The launch names a login with `containment.lead.login_warning_h` hours or fewer left (default 24), its
  time left and a fresh login as the step to take now, since OpenCode stores one as a new active row with a new
  expiry (addendum 3, ruling 2, read in the pinned bundle); it only warns. Each start stage's seconds go on the
  session's label (`start_s`) and to the debug log (addendum 3), for the five unexplained 15 to 31 s starts. The store is read as the operator's own OpenCode wrote it: a
  provider's row in a shape other than OpenCode 2.0.18's two is refused, at the start and on a request, naming the
  provider and what serves it instead, and never guessed at.
- **The Lead's own OpenCode state:** per project, between sessions; the operator's TUI preferences come in at each
  start without their plugins (a change made inside lasts the session), and their recent models are copied once,
  never their prompt history.
- **The terminal relay (R-7):** a pseudo-terminal between the operator's terminal and the TUI, bytes unfiltered, the
  window size followed, and the terminal given back (the TUI's own exit sequence and the saved settings) on every
  ending, the broker's and the reaper's deaths included.
- **Messages:** the start lines (each login and whether it is relayed, what `--provider-env` feeds, the provider
  variables set in the operator's environment and not fed, the MCP servers left out, by name; with no provider
  relayed, that only OpenCode's free models work and the operator's own `opencode auth login`); one line in the
  Lead's system text from its label; a sandbox that cannot start for want of a user namespace names
  `user.max_user_namespaces` and the fix (ST-27 fact 5).
- **ST-38 (the server password), accepted** by the designer's ruling: the residual test now asserts the sentinel and
  the password and never the key, for a worker's run and the Lead's session, and three tests pin the ruling's
  conditions (the password new per launch and in no file outside its run; no context reaching another run's server;
  no route-closing control a harness permission rule).
- **Follow-on, measured:** a stored opencode key is not served (see above); serving it needs a per-model `baseURL`
  for every opencode catalog model, mapped from a pinned copy of the catalog, never the live one (addendum 2,
  ruling 2, which targets it On measured need).
