**Built (`feat/e123-relay-client-cert`).** The policy names a provider's three files in `containment.network.client_certs.<provider>` (`cert`, `key`, `ca`). The relay reads them at its start, presents the certificate, and checks the provider's certificate against the CA file alone (`harness/containment/client_cert.py`). A certificate that can't be used refuses the launch, one line per problem, naming the file (the key by its policy field only), and `aew doctor`'s `client-cert` line shows the same lines. The certificate and key are masked from every contained run, so the launch's self-test proves them unreadable from inside. A run with no relay refuses the provider, in the engine's launch check and the supervisor's. A failed handshake reaches the harness as a 502 naming the policy field or the CA file: `client_cert_refused`, `client_cert_required`, `upstream_untrusted` or `tls_failed`. The tests use a throwaway CA and a local server that requires a client certificate.

**The 429 ladder, measured at home.** The relay passes a 429 through as the upstream sent it, `Retry-After` included, with one request upstream and no retry (`test_a_429_reaches_the_harness_as_the_upstream_sent_it_with_its_retry_after`). Not measured yet:
- whether OpenCode 2.0.18 backs off on it, and how it treats `Retry-After`. This needs a real OpenCode run against a local fake upstream on the VM, in a network namespace;
- how parallel workers share one limit;
- what the provider's own 429s look like. Only a live run against that provider can show this.

**The designer's build check, not yet run:** whether OpenCode 2.0.18 needs a placeholder key for a provider of its own id with no key variable. AEW requires none. Like the 429 measurement, this needs a real OpenCode run in a network namespace.

**Gaps this build leaves, for rows:**
- **Codex:** there is no Codex adapter yet (`harness/registry.py` names OpenCode only). One on the relay route gets this through `RunNetwork.start` as any harness does.
- **The uncontained Lead:** the Lead launched without containment (Windows, or `allow_weaker`) reaches its provider directly, with no relay, and is not refused over a configured certificate. The contained Lead's relays present it.
