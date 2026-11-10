**Built (`feat/e123-relay-client-cert`).** The policy names a provider's three files in `containment.network.client_certs.<provider>` (`cert`, `key`, `ca`). The relay reads them at its start, presents the certificate, and checks the provider's certificate against the CA file alone (`harness/containment/client_cert.py`).
- **Refusals:** a certificate that can't be used refuses the launch, one line per problem, naming the file. An upstream that isn't `https://` is one such problem. `aew doctor`'s `client-cert` line shows the same lines.
- **The key's path:** AEW's own lines name the key by its policy field. These are the refusals, doctor's line, the relay's label and its answers. The run's layout record lists the key's path among its masked paths, as it lists every mask.
- **Masks:** the certificate and key are masked from every contained run, so the launch's self-test proves them unreadable from inside.
- **No relay:** a run with no relay refuses the provider. The engine's launch check and the supervisor's both refuse it, and the supervisor checks again after `establish`, where a sandbox that couldn't be established under `allow_weaker` leaves no relay.
- **The Lead:** the contained Lead relays such a provider of its own id with no key, which the provider requires (it takes the certificate alone: the operator). The provider must have `containment.network.upstreams.<id>`, and never be one the Lead denies; its models are the ones the policy's profiles pin for it. Only under `proxy_only`: a Lead with no relay (a shared or isolated network, Windows, or an `allow_weaker` fallback) says at its start which providers it can't use. The same assumption in the Lead's key and login start lines predates this PR, and gets a row of its own.
- **Handshake failures** reach the harness as a 502 naming the policy field or the CA file:
  - `client_cert_refused`;
  - `client_cert_required`: under TLS 1.3 from the certificate_required alert, under TLS 1.2 from handshake_failure, worded as a likelihood;
  - `upstream_untrusted`;
  - `tls_failed`.
- **Tests:** they use a throwaway CA and a local server that requires a client certificate.

**The 429 ladder, measured at home.** The relay passes a 429 through as the upstream sent it, `Retry-After` included, with one request upstream and no retry (`test_a_429_reaches_the_harness_as_the_upstream_sent_it_with_its_retry_after`). Not measured yet:
- whether OpenCode 2.0.18 backs off on it, and how it treats `Retry-After`. This needs a real OpenCode run against a local fake upstream on the VM, in a network namespace;
- how runs share the provider's limit. The provider that requires a client certificate keeps one bucket per identity and per model (the operator, 2026-11-10). The identity is the client certificate, so the Lead and every worker on the same model spend one bucket together; runs on different models don't contend. The first live check watches the 429s with the Lead and two workers on the same model, then on different models, not one run alone;
- what the provider's own 429s look like. Only a live run against that provider can show this.

**The first real run's checks, not yet run:** these need a real OpenCode run in a network namespace, like the 429 measurement.
- whether OpenCode 2.0.18 resolves a provider of its own id (such as `mtls`) at all, with no SDK package named. The two projections differ, so each is checked:
  - a worker's names the provider's `baseURL` and `transport` and its one pinned model;
  - the contained Lead's names the provider's `baseURL` and `transport` and every model the policy's profiles pin for that provider (the Lead doesn't load the operator's OpenCode configuration, and the catalog doesn't know the id). If the Lead lists no model of it, this is where to look;
- whether it needs a placeholder key for one. AEW requires none.

**A gap this build leaves, for a row:** Codex has no adapter yet (`harness/registry.py` names OpenCode only). One on the relay route gets this through `RunNetwork.start`, as any harness does.
