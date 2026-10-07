# T6 — Network containment: Rocky 8 evidence and frozen Linux design (v0.2)

- **Status:** **Adopted / design frozen** by the designer, 2026-10-06 (relayed by the operator); it moved from `design/proposals/` that day. Until then this line read "**Design frozen — proposed for operator adoption**, 2026-10-04." Its §3 landed as ADR-0009's amendment of 2026-10-05 (designed, not built; register F28). The text below is unchanged: frozen 2026-10-04. The Rocky 8 probe results are accepted as evidence. This v0.2 preserves those observations and resolves the designer questions, while correcting the provider-credential proxy and in-sandbox shim semantics before implementation.
- **Where it ran:** the operator's Rocky Linux 8.10 VM (kernel `4.18.0-553.134.1.el8_10.x86_64`, bubblewrap 0.4.0, SELinux enforcing, `user.max_user_namespaces` 30,551, Python 3.11.13, OpenCode 2.0.18 at `~/opencode-2.0.18/opt/OpenCode/resources/opencode-cli`), under `~/aew-review/t6-net`, no sudo, the lead developer's suite held while it ran (`pgrep` check), scratch under `~/.aew-test-tmp/review-*` removed by the scripts. The earlier M4-B probes ran on WSL's kernel; these are the first network probes on an EL8 kernel.
- **Scripts and outputs:** `repro/t6/netns_probe.py` (P1–P5) with `netns_probe.out.txt` and `netns_probe.p5.out.txt`; `repro/t6/opencode_net_probe.py` (A1, A2, B, C, and `--catalog` D, E) with `opencode_net_probe.out.txt`, `opencode_net_probe.catalog.out.txt` and the strace `opencode_net_probe.A1.trace.txt`. Everything below marked **[probe]** is read from those files; **[doc]** is documentation; **[inf]** inference; **[rec]** recommendation; **[hyp]** open.
- **Not reopened:** M4-B's filesystem layout and labels (`os_readonly_roots`, `pid_namespace`, `network: not_provided`), ADR-0009's adapter boundary, ADR-0005 custody. This note adds a network dimension beside them.

## 1. Results

| # | Question | Result [probe] |
|---|---|---|
| P1 | What does `bwrap --unshare-net` give a run on EL8? | A namespace with only `lo` (the host has `enp0s3`, `lo`, `virbr0`). An outbound connect fails in 13 ms with `ENETUNREACH`; DNS fails in 3 ms (`Name or service not known`); binding 127.0.0.1 inside works. Nothing hangs. |
| P2 | Does the custody bridge survive the namespace? | Yes. A **filesystem** AF_UNIX socket in a 0700 directory bound read-only into the sandbox is connectable from inside (`fs-ok`). An **abstract** AF_UNIX socket is not (`ECONNREFUSED`): abstract sockets belong to the network namespace. The bridge uses a filesystem path (`bridge.private_address`), so it keeps working unchanged. |
| P3 | How does the supervisor reach the private server, which listens on the sandbox's own 127.0.0.1? | It cannot connect to `127.0.0.1:<port>` from the host (`ECONNREFUSED`: a different loopback). A forwarder **started inside the sandbox** that listens on a unix socket in a bound-in directory and connects to the server's loopback port works: 200 requests, median 1.88 ms, p95 2.76 ms, against 1.18 ms / 2.07 ms for plain host loopback. `nsenter` from outside is not available to an unprivileged supervisor (it needs `CAP_SYS_ADMIN` over the sandbox's user namespace). |
| P4 | Can egress be limited to the model gateway with the provider key kept out of the sandbox? | Yes. A host-side HTTP CONNECT proxy on a unix socket with an allowlist, an in-sandbox forwarder from `127.0.0.1:3128` to that socket, and `HTTP_PROXY`/`HTTPS_PROXY` set in the sandbox: the allowed target answers (13 ms), a second local target and `example.com` are refused with 403 in 2 ms, the sandbox's environment holds no provider key, and the gateway stand-in received `Authorization: Bearer <key>` added by the proxy. |
| P5 | Is slirp4netns an alternative? | Not as tried: `setns(CLONE_NEWNET): Operation not permitted` when attaching to bubblewrap's child from outside. It also offers no allowlist (NAT for everything), so it would not serve the goal even if attached. **[hyp]** the EPERM is the single-uid user namespace bubblewrap creates (podman succeeds because it uses `newuidmap`); not pursued. |
| A1 | What does `opencode-cli serve` 2.0.18 fetch at startup with a shared network? | Exactly one thing: after a DNS query to the host's resolver, two TLS connections each to two Cloudflare addresses (IPv4 and IPv6), identified by A2 as **`models.opencode.ai:443`** (the model catalog). With `autoupdate: false`, `share: disabled`, `lsp: false`, `formatter: false` and `OPENCODE_DISABLE_AUTOUPDATE=1`, nothing else. Server up in 1.35 s; `/api/info` 200. |
| A2 | Does the Bun runtime honour proxy variables? | **Yes.** With `HTTP_PROXY`/`HTTPS_PROXY` set to a host proxy the strace shows **no** non-loopback connect, and the proxy log shows `CONNECT models.opencode.ai:443`. This is what makes P4's design usable for OpenCode without patching it. |
| B | Does `serve` work with no network at all? | Yes. Under `--unshare-net` with fresh private XDG state it announces in 0.43 s, answers `/api/info`, and `/api/model` lists 7 models (the `opencode` provider's embedded catalog) in 1.1 s. Nothing hangs or crashes; the server log is empty. |
| C | Does a seeded catalog change that? | Copying A1's `data/opencode/opencode.db` (where the fetched catalog is stored) into the offline run gives 10 models instead of 7. The catalog cache lives in the per-run database, not under `XDG_CACHE_HOME`. |
| D | With a configured provider (a dummy `OPENAI_API_KEY` in the server's environment) and network? | 89 models, providers `openai` and `opencode`, including `gpt-6.1-sol`, `gpt-6.1-sol-fast`, `gpt-6.1-sol-pro`, `gpt-6-luna…`, `gpt-6-sol…`. Catalog in 1.1 s. |
| E | Same, with `--unshare-net`? | 62 models from the **embedded** catalog: `gpt-6-luna…`, `gpt-6-sol…`, `gpt-6-astra…`; **the `gpt-6.1-*` models are absent**. The adapter's pinned-model check (the model and variant must appear in `/api/model`) would therefore **fail closed offline for a model newer than the binary's embedded catalog**, and pass for an older one. |

### 1.1 Design-authority correction: CONNECT allowlisting and provider credential injection are separate jobs

P4 establishes two useful observations: a private run can reach a supervisor-owned unix-socket proxy through an in-sandbox loopback forwarder, and Bun/OpenCode honours `HTTP_PROXY`/`HTTPS_PROXY`. It does **not** justify a production design in which a conventional HTTPS CONNECT proxy injects `Authorization` into end-to-end TLS traffic. Once CONNECT establishes a tunnel, the provider request is encrypted between the harness client and the upstream; a non-MITM CONNECT proxy cannot add an HTTP Authorization header inside that TLS stream.

The frozen design therefore separates:

1. **credentialing provider relay** — the harness points its configured provider `baseURL` at an in-sandbox loopback endpoint. A secretless in-sandbox shim forwards plaintext provider-protocol bytes over AF_UNIX to a supervisor-owned **reverse relay**. The reverse relay has a fixed configured upstream, strips/replaces any client Authorization, adds the real provider credential, establishes TLS to the gateway, and streams the response back. The sandbox receives at most a non-secret sentinel credential if the harness/SDK syntactically requires one.
2. **generic allowlisted egress proxy** — optional HTTP(S) CONNECT egress for explicitly authorized non-provider destinations such as a connected-mode model-catalog fetch. It holds **no provider credential** and never injects one.

The provider relay does not accept an arbitrary upstream URL from the sandbox. Its upstream/provider mapping is fixed by the execution profile and supervisor configuration, preventing the model from turning the credentialing relay into an SSRF or credential-forwarding oracle.

Two facts from the T1 and M4-B work that this note relies on without re-deriving: the adapter talks to the server over `http://127.0.0.1:<port>` and asserts the announced URL is loopback (`client.py` `LOOPBACK_URL`); the M4-B layout shares the network namespace by design and labels it `network: not_provided`.

## 2. What the results settle

1. **`--unshare-net` is viable on EL8 for the whole run tree** (P1, B): nothing in OpenCode's startup needs the network when the catalog is embedded or seeded, and the sandbox fails fast rather than hanging. The containment research's §3.2 note "network stays shared … the harness needs the model API" is true, but the need is satisfiable through a bound-in socket (P4), not only through a shared namespace.
2. **The custody bridge needs no change** (P2). The supervisor–server link needs **one new piece**: an in-sandbox forwarder (P3), since the server listens on the sandbox's loopback. Cost about 0.7 ms per request.
3. **The provider key can leave the sandbox entirely** (P4, A2): the proxy adds it. This closes REVIEW G5's exfiltration path (an agent with a shell in the sandbox reading the server's environment or `/proc/<pid>/environ`) and the N1 lead in one step, for OpenCode as it is.
4. **The allowlist is the gateway and nothing else** (P4): `models.opencode.ai` is the only other startup destination (A1), and it is unnecessary when the catalog is seeded (C, E). An air-gapped deployment seeds it (T10 §5); a connected one may allow it or not.
5. **Offline model availability is a catalog question, not a network one** (D, E): the embedded catalog is a snapshot at the binary's build; a pinned model newer than that needs a seeded `opencode.db` catalog (C) or the fetch allowed once. `aew doctor` must say which (T10 §6, "Credentials / gateway" row).

## 3. Frozen design (F-F)

### 3.1 Truthful network labels

The run containment label gains:

```text
network.mode:
    proxy_only | isolated | shared | not_provided

network.provider_relay:
    configured | none

network.egress_allow:
    [host:port, ...]       # only when generic allowlisted egress exists
```

Meanings:

- `proxy_only` — private network namespace; provider traffic is possible only through the supervisor-owned credentialing relay; any additional egress is through the separate explicit allowlist proxy.
- `isolated` — private network namespace with loopback/control sockets only and no external egress path.
- `shared` — the run shares the host network namespace. This is truthful topology, **not** a containment guarantee.
- `not_provided` — AEW cannot enforce/characterize network containment on this backend/platform (the initial Windows state).

Until F-F is implemented, existing Linux M4-B runs should be labelled `shared`, not retroactively described as `proxy_only`. Once F-F is accepted, Linux model-controlled harness runs default to `proxy_only`; `shared` becomes an explicit weaker execution-policy choice.

### 3.2 Layout and one secretless in-sandbox network shim

The M4-B `Layout` gains a network mode and the AF_UNIX paths required by that mode. `bwrap_argv` adds `--unshare-net` for `proxy_only` and `isolated`.

A small AEW-owned **network shim** runs inside the same private network namespace as the harness for the lifetime of the run. It is a sibling/lifecycle-owned process, not a wrapper that `exec`s away. It provides only the endpoints configured for that run:

- host/supervisor → bound AF_UNIX socket → shim → harness `127.0.0.1:<server-port>`;
- harness provider baseURL `127.0.0.1:<provider-port>` → shim → bound AF_UNIX socket → supervisor credentialing relay;
- optional `127.0.0.1:<egress-port>` → shim → bound AF_UNIX socket → supervisor generic allowlist proxy.

The shim has no provider credential, no Lead credential and no policy authority. The supervisor's existing ProcessTree owns both shim and harness; ending the run ends both. Codex may use native `unix://` app-server transport and omit the supervisor→server leg when the pinned adapter proves it, but that is an optimization over the same semantics.

### 3.3 Supervisor-owned credentialing provider relay

For `proxy_only`, the supervisor starts one credentialing relay per required provider/profile (or an equivalently isolated multiplexed implementation with the same fixed mapping):

```text
sandbox client
   ↓ local secretless HTTP endpoint
AF_UNIX
   ↓
supervisor provider relay
   - fixed upstream from execution profile
   - holds provider credential
   - strips/replaces client Authorization
   - TLS to gateway
   - streaming passthrough
```

The provider key is never copied into the harness/server/model-controlled environment or filesystem. The relay is outside the run's PID/network namespace and follows the existing credential-holder custody rules.

This relay is provider/model traffic infrastructure, not a general web proxy. It cannot be directed by the model to arbitrary hosts.

### 3.4 Generic allowlisted egress is separate and credentialless

If policy authorizes non-provider network access, a separate supervisor-owned egress proxy may permit a bounded `host:port` allowlist. It holds no provider secret.

For OpenCode 2.0.18 connected mode, `models.opencode.ai:443` may be allowed solely for catalog refresh. Air-gapped mode instead uses the pinned catalog seed in §3.7. Web fetch/browser/package-manager destinations are **not** implicitly added because the harness happens to support those tools; they require their own authorized capability/policy.

### 3.5 Adapter behavior

OpenCode:

- provider `baseURL` is projected to the local provider-relay endpoint for `proxy_only`;
- any SDK-required API-key value inside the sandbox is non-secret/sentinel material;
- `HTTP_PROXY`/`HTTPS_PROXY` are used only for the separate generic egress proxy when such egress is authorized;
- `NO_PROXY` includes the harness/server/provider-relay loopback endpoints as appropriate;
- the real `provider_env` goes only to the supervisor credentialing relay.

Codex follows the same AEW boundary. Native `features.network_proxy` or native sandbox domain rules are optional defence-in-depth behind AEW's namespace/relay semantics, never the credential holder or authoritative label.

### 3.6 Self-test and readiness

The containment self-test must prove the boundary without depending on a provider-specific `HEAD` implementation:

1. direct non-loopback egress from inside the sandbox fails;
2. the AEW bridge answers through the filesystem AF_UNIX path;
3. the supervisor↔harness server path through the shim works;
4. a supervisor-owned local probe upstream succeeds through the provider-relay path;
5. an unauthorized generic-egress target is refused;
6. the sandbox/model-controlled environment and readable files contain no provider secret.

Provider/gateway readiness is a separate adapter/doctor check against whatever bounded health/catalog operation that provider profile supports. Failure is explicit and fail-closed; it is not conflated with the containment self-test.

### 3.7 OpenCode catalog for connected and air-gapped profiles

The OpenCode 2.0.18 probe shows that offline model availability is bounded by the binary's embedded/seeded catalog. For an air-gapped release, AEW may package a **sanitized, checksum-pinned catalog seed produced from a clean disposable instance of the exact supported OpenCode pin**. It must not copy an operator's arbitrary `opencode.db`.

The seed artifact is compatibility data tied to the OpenCode pin and bundle manifest. `aew doctor` verifies its fingerprint/pin and verifies that the configured model/variant appears in the effective catalog. If a later supported OpenCode version provides an official offline-catalog mechanism, prefer that and retire the internal DB seed for that pin.

### 3.8 Project checks

Checks default to:

```text
network: isolated
```

not to the parent harness's effective network mode. A check may request `proxy_only` or `shared` only when the project check definition and execution policy permit it. The effective mode may be equal to or **stricter than** the execution-policy network ceiling; a check cannot silently widen network authority inherited from the surrounding run.

The actual check network mode and allowed egress are recorded with check evidence.

### 3.9 Lead session

The Lead harness is model-controlled execution and therefore uses the same default `proxy_only` provider path on Linux once F-F is built. The fact that the human operator owns the TUI does not make model-controlled shell/processes safe holders of provider credentials.

Operator-facing UI/attach traffic remains outside that model-execution boundary. If the Lead needs broader research/network capability, it receives an explicit bounded capability/tool path; raw shared network is not implied by being the Lead.

## 4. Costs and what is not shown

- Per-request overhead on the supervisor↔harness path is about 0.7 ms in P3. Provider-relay overhead against a real TLS gateway is unmeasured; P4 was a local stand-in and must not be treated as proof of production credential injection through HTTPS CONNECT.
- Not shown: a real streamed model turn through the frozen credentialing reverse relay; backpressure/cancellation behavior under long streaming responses; IPv6-specific upstream cases; and Windows network containment (`network: not_provided` remains until a separate backend exists). These are implementation/conformance probes, not open authority questions.
- slirp4netns is recorded as not working out of the box and not needed (P5).

## 5. Register entry text (F-F, frozen candidate)

> **F-F. Network containment (Linux).** Model-controlled runs use a private network namespace. Provider/model traffic crosses a secretless in-sandbox loopback/AF_UNIX shim to a supervisor-owned credentialing reverse relay whose upstream is fixed by the execution profile and which holds the provider credential; optional non-provider egress uses a separate credentialless allowlist proxy. The supervisor reaches a loopback-only harness server through the same secretless shim where the harness lacks native unix-socket transport. Labels distinguish `proxy_only`, `isolated`, `shared` and `not_provided`; self-test proves direct egress denial, bridge/server paths and secret absence. Checks default `isolated` and cannot widen past execution policy. OpenCode 2.0.18 air-gap bundles carry a sanitized checksum-pinned catalog seed tied to the supported binary. Rocky 8.10 probes establish namespace viability, filesystem AF_UNIX survival, the server forwarder (~0.7 ms/request), OpenCode no-network startup, its only observed startup fetch (`models.opencode.ai`) and Bun proxy-variable support. Depends on M4-B. Required before internal alpha. ADR-0009 label/custody amendment.

## 6. Frozen designer decisions

1. **Linux default after F-F: `proxy_only`.** Before F-F lands, existing Linux M4-B behavior is truthfully `shared`. `shared` remains an explicit weaker policy mode, not the default.
2. **Lead included.** The Lead harness also defaults to `proxy_only` because its model-controlled shell/processes must not hold or freely exfiltrate provider credentials. Operator UI ownership does not change that boundary.
3. **Checks default `isolated`.** They may request a network mode only within the execution-policy ceiling; check evidence records the effective mode.
4. **Catalog seed accepted with qualification.** For OpenCode 2.0.18, use only a sanitized seed generated from the exact pinned binary in a clean disposable instance, checksum it in the air-gap bundle, and validate it in `aew doctor`. Prefer an official offline catalog mechanism on future pins if one exists.
5. **Provider credentialing and generic egress are separate mechanisms.** Do not implement the production key-custody claim as header injection inside a conventional HTTPS CONNECT tunnel.
6. **Network containment is a pre-internal-alpha requirement, not an M4-C/D blocker.** It may be implemented in the F-F/hardening lane once the current M4 dependency permits, but no internal-alpha security claim should call Linux runs network-contained before it passes its live lane.

No further designer-level question remains in T6. The real-gateway streaming test, shim lifecycle details, IPv6 cases and future Windows backend are implementation/conformance work.
