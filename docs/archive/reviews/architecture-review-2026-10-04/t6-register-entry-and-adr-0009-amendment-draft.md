# T6 → artifacts: the register entry and the ADR-0009 amendment text (drafts)

- **Status:** text for two documents the lead developer owns, written by the independent architecture review from `T6-network-containment.md` (the probes on Rocky 8.10) and the live checkout's M4-B amendment to ADR-0009 (`impl/m4-b-containment` at `56b85ad`, read-only). **Direction accepted by the designer, 2026-10-04:** the provider-key residual is real and the relay is justified; the server-password residual stays explicitly open; the containment labels change as proposed; the final text keeps the **fixed-upstream credential relay** distinct from **generic allowlisted egress**. §2 below is that final text. Not governing until adopted; nothing in the live repository was changed. TRIAGE §3 item 2.
- **What changed since the T6 note was written:** the T6 note was drafted against `dcd43f1`, which has only the M3 containment section of ADR-0009. The live branch's M4-B amendment (2026-10-03) adds a **documented residual** that this work closes for the provider key: "the harness server's environment is readable from the agent's shell … the provider key the policy names, and the server password … one read of `/proc/<parent>/environ` away … closing this needs the server outside the agent's user or namespace", asserted by `test_residual_the_harness_servers_environment_is_readable_from_the_agents_shell`. The egress proxy is a third way to close it: the key is not in the server's environment at all. The server password stays there; the amendment below says so.
- **Not reopened:** M4-B's layout, bind order, labels for `filesystem` and `process_ownership`, the fail-closed launch, ADR-0005 custody, ADR-0009's adapter boundary. The amendment adds the `network` dimension and changes one label value's meaning (`not_provided`).

Legend: **[probe]** read from `repro/t6/*.out.txt`; **[doc]** from the live ADR-0009 or the schemas; **[inf]** inference; **[rec]** recommendation; **[Q]** for the designer.

## 1. Register entry (`docs/implementation/future-work.md` §2 "Designed, not implemented")

The register's ids run F1–F20 on the live branch **[doc]**; the review's internal label was F-F (`REVIEW.md`). The row below uses the next free id as a placeholder.

| # | Work | Source (governing) | Belongs to or gated by | Notes |
|---|---|---|---|---|
| F21 | Network containment (Linux): a private network namespace per run, egress only through a supervisor-owned allowlisting proxy that holds the provider credentials outside the sandbox, the supervisor reaching the run's harness server through an in-sandbox forwarder; `network: proxy_only` on the label; a self-test row; a `network` setting per project check | ADR-0009 amendment (below), once adopted; isolation design §3.2's "network stays shared" note, superseded by the probes | **Before internal alpha** (REVIEW §8). Depends on M4-B (built). Independent of M4-C's workspace strategy | Closes the ADR-0009 M4-B residual for the provider key (not for the server password). Probed on Rocky 8.10, kernel 4.18, bwrap 0.4.0, OpenCode 2.0.18: `--unshare-net` leaves `lo` only and fails fast (`ENETUNREACH` 13 ms); the filesystem AF_UNIX bridge survives; an in-sandbox forwarder costs about 0.7 ms per request; the proxy allowlist works with the key injected outside; OpenCode starts with no network when its catalog is embedded or seeded; its only startup fetch is `models.opencode.ai`; Bun honours `HTTPS_PROXY`; slirp4netns is not needed and does not work under bwrap unprivileged (`AEW-reviews/architecture-dcd43f1/T6-network-containment.md`, `repro/t6/`). Not shown: a real model turn through the proxy, IPv6, Windows (stays `not_provided`). |

**[rec]** When the row lands, the M4-B closing row for F2 in §9 gains the sentence "Network: F21." so a reader of the closed F2 does not take filesystem containment for containment.

## 2. ADR-0009 amendment (draft text, to follow the 2026-10-03 M4-B amendment)

> ## Amendment <date> — network containment on Linux (F21; independent architecture review T6)
>
> M4-B's amendment says a contained run's network is shared and labels it `network: not_provided`, and records a residual: the harness server's environment, with the provider key, is readable from the agent's shell. This amendment adds the network dimension to containment and closes that residual for the provider key. It was probed on Rocky Linux 8.10 (kernel 4.18, bubblewrap 0.4.0, SELinux enforcing) with OpenCode 2.0.18 (`AEW-reviews/architecture-dcd43f1/T6-network-containment.md`); the implementation is F21.
>
> ### What F21 claims, exactly
> - **Egress control.** A contained run can reach only the destinations its policy allows, through one proxy the supervisor owns, and nothing else: no route exists from the run's namespace to any network. A connect to anything but the proxy fails at the OS (`ENETUNREACH`), as a forbidden write fails with `EROFS` under F2.
> - **Two kinds of allowed destination, never merged.** A **relay upstream** is a provider gateway fixed by the configured provider (OpenCode's `providers.<id>.settings.baseURL`, or the provider's default endpoint); the proxy attaches that provider's credential to requests for it and for nothing else. A **generic egress host** is anything the operator lists in `egress_allow` (the model catalog host, a package index): forwarded as sent, no credential ever attached, no credential header passed through. The relay set comes from provider configuration and cannot be extended from `egress_allow`; a host in both is a policy error at launch.
> - **Credential custody for the provider key.** The provider variables the execution policy names (`provider_env`) are never in the sandbox: not in the agent's environment (M3), and no longer in the harness server's. The proxy holds them outside the sandbox and sends them only to the relay upstream. The ADR-0005 bridge is unchanged and still the only path for AEW credentials.
> - **Not confidentiality of traffic.** The proxy sees request lines and headers for allowed hosts and forwards bodies as they are; it does not inspect, store or rewrite them beyond the credential header. Logging is the run log's business and records hosts, not bodies.
> - **Not a claim about the server password.** The harness server still runs inside the run's PID namespace as the same user, and its own password (`OPENCODE_PASSWORD`) is still one read of `/proc/<parent>/environ` away. That residual **remains open** after this amendment; the M4-B residual paragraph narrows to it and its test asserts the narrowed fact.
> - **Not Windows.** Windows has no network namespace; its runs stay `network: not_provided`.
>
> ### The namespace (`layout.py`, `bwrap_argv`)
> - `Layout` gains `unshare_net: bool` and `egress: tuple[str, ...]` (the allowlist, `host:port`). `bwrap_argv` adds `--unshare-net` when set: the sandbox has `lo` only. Binding on the sandbox's own loopback works; DNS and outbound connects fail in milliseconds, so nothing hangs waiting for a network that is not there.
> - **Two sockets cross the boundary, both filesystem AF_UNIX, both bound in read-only:** the ADR-0005 bridge (already) and the egress proxy's socket. A filesystem unix socket is reachable across a network namespace; that is what makes `--unshare-net` viable without slirp4netns or a veth pair (which need privileges the sandbox does not have).
>
> ### The egress proxy (supervisor, outside the sandbox)
> - For a `proxy_only` run the supervisor starts, as its own child outside the sandbox, one HTTP proxy on a unix socket under the run's directory, with two tables: **relay** (`host:port` → the provider credential to attach, from provider configuration) and **allow** (`host:port`, from `egress_allow`). A request for a relay upstream is forwarded with the credential header added (and any credential header the run sent replaced); a request for an allowed host is forwarded as sent; every other destination gets 403. CONNECT to a relay upstream is refused, because a tunnel cannot carry an injected header: the relay is plain forward-proxying over the proxy's own TLS to the upstream. It ends with the run (`--die-with-parent` on the sandbox side, the run's process group on the host side).
> - Defaults: the relay table is exactly the configured providers' gateways; the allow table is empty. For OpenCode 2.0.18 the only other startup destination is `models.opencode.ai`, unnecessary when the catalog is embedded or seeded, so an air-gapped project seeds the catalog and allows nothing; a connected project may list the catalog host under `egress_allow` as generic egress.
> - A tool that fetches (`webfetch`, a package install inside a check) hits the proxy and is a generic egress decision: denied unless its host is allowed, and never credentialed. That is the intended place for the decision.
>
> ### The forwarder (inside the sandbox)
> - The harness server listens on the sandbox's loopback, which the supervisor cannot reach. The sandbox's PID 1 is a small forwarder (`aew-run netfwd`, stdlib only) that listens on a bound-in unix socket for the supervisor's client and on a fixed loopback port for the proxy, then `exec`s the harness command. The supervisor's `Client` connects over the unix socket; `Server.start` reads the announced port and hands it to the forwarder. The `--stdio` lease is unchanged: the forwarder's stdin is the server's. Measured cost about 0.7 ms per supervisor request.
>
> ### Adapters
> - OpenCode: `server_env` sets `HTTP_PROXY`/`HTTPS_PROXY` to the forwarder's loopback port and `NO_PROXY=127.0.0.1,localhost`, and drops `provider_env` from the server's environment. The Bun runtime honours `HTTPS_PROXY` for the provider gateway and the catalog host.
> - A second adapter (Codex app-server) uses the same proxy; its own `features.network_proxy` domain rules are a second line behind the namespace, never the first. Its app-server over `unix://PATH` would remove the forwarder's server leg.
>
> ### Policy (`containment` in the execution policy)
> - `network: proxy_only | shared` (Linux; the default is a designer decision, below). `egress_allow: [host:port, …]` lists generic egress hosts; it cannot name a relay upstream, and the relay set is not a policy field (it is derived from provider configuration, so an operator cannot point the credential at another host by editing the allowlist). `proxy_only` with `mode: allow_weaker` and no namespace available launches labelled `shared`, with the reason recorded, as `allow_weaker` does for the filesystem.
> - **Checks:** `checks.yaml` gains `network: none | proxy_only | shared` per check, default `none` (a test command needs no network); the setting is recorded on the check's evidence beside `method.containment`.
>
> ### Labels
> - `network` takes three values: **`proxy_only`** (namespace plus proxy, with `egress: {relay: [host:port…], allow: [host:port…], proxy: <socket path>}` recorded beside it, so the record says which destinations were credentialed and which were plain), **`shared`** (the host's network, declared), **`not_provided`** (AEW has not addressed the network: Windows, and platforms without namespaces).
> - **Meaning change for M4-B records.** Until F21 lands, a Linux run contained under M4-B has the host's network and is labelled `not_provided`. From this amendment on, a contained Linux run with a shared network is labelled **`shared`**: the distinction is between a network AEW declares and one it has not addressed. Records written before this amendment with `network: not_provided` on Linux read as `shared`; nothing is rewritten.
> - `aew harness status` shows the network mode and, for `proxy_only`, the allowlist. A check result's `method.containment.network` says where the check's traffic could go.
>
> ### Self-test
> - The launch self-test gains a network row for `proxy_only`, run inside the exact layout before any harness process exists: a connect to a disallowed host must fail at the OS without the proxy and with 403 through it; the allowed gateway must answer a `HEAD` through the proxy; the bridge must answer `whoami`. Any failure ends the run `launch_failed` with `CONTAINMENT_UNAVAILABLE` and the reason, as today.
> - `aew doctor` reports the network mode, whether the proxy socket can be created, and whether OpenCode's catalog is embedded or seeded for the pinned model (an air-gapped project with a model newer than the binary's embedded catalog needs the seeded `opencode.db`).
>
> ### Residual risk after this amendment
> - **The server password is still readable from the agent's shell** (same PID namespace, same user). This residual is **open**, not narrowed away: closing it needs the server outside the agent's namespace or user, which is not this amendment. `test_residual_…` asserts that the provider key is absent from the parent's environment under `proxy_only` and that the password is still present.
> - **The proxy is a new trusted component.** It holds the key and parses HTTP. It is stdlib code owned by the supervisor, runs as the operator's user outside the sandbox, and is reachable only through a socket bound read-only into the run; its relay and allow tables are in the run record. Because the credential is attached only for relay upstreams, a bug in the allow path cannot leak the key; a bug in the relay path can leak it to the provider's own upstream only.
> - **Not shown by the probes:** a full model turn through the proxy against a real gateway (the gateway stand-in was local), OpenCode's behaviour when a mid-run fetch is refused (the startup trace shows none), IPv6.
>
> ### Tests
> - `tests/integration/test_containment.py` (Linux): the namespace has `lo` only; a disallowed connect fails `ENETUNREACH`; the bridge answers across the namespace; the forwarder carries the supervisor's requests; a `proxy_only` run's server environment has no provider variable; the proxy attaches the credential for the relay upstream, forwards an allowed host without it and strips a credential header the run tried to send there, refuses every other host, and refuses CONNECT to a relay upstream; a policy naming a relay upstream in `egress_allow` is refused at launch; the self-test row fails closed; a check with `network: none` cannot reach the proxy.
> - `tests/unit/test_containment_layout.py`: `unshare_net` in `bwrap_argv`, the label values, the `not_provided → shared` read of old records.
> - The residual test narrows as above.

## 3. Schema and code deltas the amendment implies (so the Ticket is sized)

| Where | Delta |
|---|---|
| `src/aew/schemas/execution.schema.json` `containment` | `network: {enum: [proxy_only, shared]}`, `egress_allow: {array of "host:port", uniqueItems}` (generic egress only; relay upstreams are derived from the providers' configuration, not a policy field) |
| `src/aew/schemas/checks.schema.json` per check | `network: {enum: [none, proxy_only, shared]}` |
| `src/aew/harness/containment/__init__.py` | `PROXY_ONLY = "proxy_only"`, `SHARED = "shared"`; `label(..., network=..., egress=...)`; the legacy reader maps Linux `not_provided` to `shared` |
| `src/aew/harness/containment/layout.py` | `unshare_net`, `egress`, the proxy socket bind, `--unshare-net` in `bwrap_argv` |
| `src/aew/harness/containment/probe.py` | the network row |
| `src/aew/harness/supervisor.py` | start the proxy; connect the `Client` over unix; hand the forwarder its port |
| new `src/aew/harness/egress.py`, `src/aew/harness/netfwd.py` (`aew-run netfwd`) | the proxy (about 150 lines: two tables, relay forward with header injection, allow forward as sent, 403 otherwise) and the forwarder (about 60; the probe's version is `repro/t6/netns_probe.py` P3) |
| `src/aew/harness/opencode/adapter.py` `server_env` | the proxy variables; drop `provider_env` under `proxy_only` |
| `src/aew/policy/checks.py` | per-check network mode into the check's layout and evidence |
| `aew doctor` | network mode and catalog rows |

**[inf]** Nothing here touches control state, the manifest, DispatchDecision or the Lead surface; the Ticket is Class 2 by the lead guide's own table (a security boundary), not Class 0, whatever its diff size.

## 4. Decisions needed before the Ticket (carried from T6 §6, with the review's recommendation)

Decided by the designer on 2026-10-04: the amendment direction, the relay's justification, the labels as proposed, the server-password residual kept explicitly open, the relay/egress distinction in the final text. Still open:

1. **[Q] Default for Linux runs:** `proxy_only` once built, `shared` an explicit policy choice. **[rec]** `proxy_only`, because the run record then says what the operator believes about the network, and the F2 precedent is `mode: required` by default.
2. **[Q] The Lead's own `aew opencode` session:** behind the proxy or not. **[rec]** Not in F21: the operator's TUI uses the operator's key on the operator's network; the exfiltration argument applies, but the Lead has no sandbox to put the forwarder in. A separate register note.
3. **[Q] Checks' default network:** `none` (this draft) or the run's mode. **[rec]** `none`; a check that installs packages declares it.
4. **[Q] Catalog seeding** (a copied `opencode.db`) as the air-gap mechanism, versus asking for an offline catalog file in a later OpenCode. **[rec]** Seeding now, recorded by `doctor`; T10 §5 already assumes it.
5. **[Q] Relabel M4-B records:** read `not_provided` as `shared` for Linux (this draft) or leave old records as written and start `shared` at the amendment. **[rec]** Read-as, no rewrite; the ADR already does this for the M3 string label.
6. **[Q] Register id:** F21, or keep the review's F-F through to the register.
