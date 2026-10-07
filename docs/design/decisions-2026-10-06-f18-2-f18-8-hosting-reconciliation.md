# Designer decisions of 2026-10-06: install and bootstrap v0.3 against hosting v0.6 (F18.2), and the Provider Gateway (F18.8)

**Status:** Decision record, governing. **Adopted** by the designer on 2026-10-06 and confirmed by the operator for
filing the same day. It answers the decisions-due items F18.2 (where the install and bootstrap design v0.3 collides with
the F18 hosting design v0.6) and F18.8 (how network containment's credentialing relay relates to v0.6's gateway). §1
and §2 are the decisions recorded as given; §3 says where they are filed.

## 1. F18.2: a narrow amendment of install and bootstrap v0.3

> **F18.2 — reconcile install/bootstrap v0.3 with hosting v0.6**
>
> The older install/bootstrap design needs a narrow amendment. It is not replaced wholesale.
>
> **1. “No background service” is no longer a production-hosting invariant**
>
> Replace that rule with:
>
> AEW requires no always-on harness/model daemon, but a production attachment may require attachment-scoped or socket-activated supervisor-side services for the lifetime of the authority/custody they own.
>
> In particular, the v0.6 production hosting path requires a supervisor-side control boundary and provider gateway while an attachment is ACTIVE/PREPARING, and potentially while detached children still require custody.
>
> Those components may be implementation-wise attachment-scoped, socket-activated, or otherwise lifecycle-managed. F18-B0/B1 may choose the concrete Rocky 8 mechanism.
>
> They are not required to remain running forever after all attachment/child custody ends.
>
> So the older absolute statement “AEW has no background service” is superseded. The preserved intent is no unnecessary always-on model/harness daemon, not “all AEW authority must live in the invoking terminal process.”
>
> **2. The operator terminal is not the Lead session**
>
> The older wording that treats the invoking terminal as the Lead session is also superseded by Q12/F18 hosting.
>
> The identities are now:
>
> ```
> operator terminal/session
>         |
>         | operator-only lifecycle control
>         v
> supervisor / attachment authority
>         |
>         v
> Lead harness + model session
> ```
>
> The terminal is the operator control surface.
>
> The harness/model session is the Lead execution host.
>
> They may have related lifetimes, but they are not the same authority object.
>
> **3. `aew doctor` must validate an ownership/permission matrix, not “owned by current user”**
>
> The current rule that errors merely because `.aew/` is owned by another user is incompatible with production principal separation.
>
> Amend `doctor` so it validates the expected security-principal relationship, not one universal owner UID.
>
> At minimum it must prove:
>
> * supervisor-authoritative/protected state has the configured protected ownership/ACL;
> * the Lead-host identity cannot write the protected set;
> * the operator can perform the lifecycle operations it is authorized for;
> * ordinary project/source access needed by the harness still works;
> * any project-visible derived/read-only AEW projection cannot be mistaken for or modify canonical state.
>
> The `.aew/` root itself does not need a universal ownership rule. A deployment may keep operator-owned project-facing material while protecting authority-bearing subpaths separately, or use another qualified layout.
>
> “Owned by another UID” is therefore not inherently an error.
>
> The error is:
>
> the effective ownership/ACL/principal arrangement does not satisfy the configured AEW authority boundary.
>
> This amendment should also make `aew doctor` run the B0 negative checks or their bounded equivalent against the actual Lead-host identity.

## 2. F18.8: one AEW Provider Gateway

> **F18.8 — F28 relay vs F18 gateway**
>
> These must not be two independent provider-credential holders.
>
> Adopt one logical component:
>
> **AEW Provider Gateway**
>
> The F28 fixed-upstream credentialing relay and the F18 request gateway/attestor are two responsibilities of the same provider-traffic authority boundary.
>
> The composed path is:
>
> ```
> model-controlled harness
>         |
>         | secretless local provider endpoint
>         v
> F28 namespace / AF_UNIX shim
>         |
>         v
> AEW Provider Gateway
>         |
>         | 1. identify attachment/run + qualified pin
>         | 2. normalize and attest request surface
>         | 3. deny before egress on mismatch
>         | 4. select the fixed configured upstream
>         | 5. attach the real provider credential
>         | 6. originate upstream TLS/mTLS
>         | 7. observe the provider response
>         | 8. create single-use tool-call/argument bindings
>         v
> configured provider / organization gateway
> ```
>
> The provider credential has one custody owner: the AEW Provider Gateway.
>
> This preserves F28's existing rule that the real provider credential is outside the model-controlled harness and is applied only on the fixed provider upstream. F28 already requires a supervisor-side fixed-upstream credentialing relay and a completely separate credentialless generic-egress path.
>
> F18 adds additional responsibilities to that provider path:
>
> * pre-egress model/profile/request-surface enforcement;
> * request attestation;
> * response observation;
> * server-side single-use broker binding.
>
> It does not introduce a second credential store or second credentialing proxy.
>
> **Generic egress stays separate**
>
> F28's generic allowlisted egress remains a different service/path:
>
> ```
> model-controlled process
>         |
>         v
> credentialless generic-egress proxy
>         |
>         v
> explicit allowlisted non-provider destination
> ```
>
> It never receives provider credentials and cannot widen or select the Provider Gateway's fixed upstream.
>
> That separation is already a deliberate F28 invariant.
>
> **Implementation freedom**
>
> The Provider Gateway may internally have separate modules/processes for:
>
> * request parsing/attestation;
> * fixed-upstream relay/TLS;
> * response/tool-call binding;
>
> but that is an implementation detail.
>
> Normatively:
>
> * there is one logical provider path;
> * only that boundary may access provider credentials;
> * the model-controlled host cannot bypass it;
> * the generic-egress path cannot access the credential store;
> * splitting the implementation must not create a TOCTOU gap between the request that was attested and the request that was actually credentialed/forwarded.
>
> Prefer a single composed service unless measurement or platform constraints justify a split.
>
> **Filing consequence**
>
> F28's “provider credential relay” is not deleted. Its containment/network semantics remain governing.
>
> F18.8 states that the F18 load-bearing gateway extends/composes that relay into the Provider Gateway.
>
> So:
>
> F28 owns the network-containment and fixed-upstream credential-routing requirements. F18 owns attachment-aware request attestation and broker binding. One Provider Gateway implements both contracts. Generic allowlisted egress remains separate and credentialless.

## 3. Filing (lead developer)

- **Install and bootstrap v0.3** stays governing for `aew init`, `aew doctor` and preflight, as amended by §1. Its
  status line points here. Its frozen text is unchanged; where it says there is no daemon and the Lead session is the
  operator's terminal (§7, ledger IBU-16), and where a `.aew/` owned by another user is a doctor ERROR (§6's permissions
  row, IBU-14), §1 governs. The doctor matrix of §1.3 is build work on register F18.2, and its negative checks are the
  F18-B0 checks of F18.6. Until F18.6 builds the principal separation, the rest of F18.2's doctor stays an M4-G
  candidate; the matrix and the negative checks wait for F18.6.
- **§6's other `.aew/` row (lead developer's reading).** The decisions-due item also named §6's Filesystem row, "`.aew/`
  not writable", whose obvious remedy (make `.aew/` writable to whoever runs doctor) is the same-principal collapse v0.6
  forbids. §1.3 judges "the effective ownership/ACL/principal arrangement" against the configured authority boundary,
  so it governs writability too: doctor checks that each principal can write what the matrix gives it (the operator's
  lifecycle operations, the supervisor's protected state, the harness's ordinary project paths) and that the Lead-host
  identity cannot write the protected set, and never treats `.aew/` as a whole needing to be writable by the invoking
  user. A remedy never widens the Lead host's write access to the protected set.
- **The Provider Gateway** is one logical component that register F18.8 builds as the composition of F28's
  credentialing relay with F18's gateway; F28 keeps the network-containment and fixed-upstream credential-routing
  requirements, F18.8 the attachment-aware attestation and broker binding, and F28's generic egress stays a separate,
  credentialless path. ADR-0009 records it as an amendment. F18.4's provider-access profile reaches the provider through
  the same gateway.
- Both decisions-due items are removed. Ledger prefix HRC.
