# Operator decision of 2026-10-07: the internal-alpha threat model (F23)

**Status:** Decision record, governing. **Adopted** by the operator on 2026-10-07 as the internal-alpha threat-model
disposition; F23 is closed by it. §1 is the decision as given; §2 says where it is filed and records the lead
developer's readings where it meets what is already adopted.

## 1. The decision, recorded as given

> F23 is now decided. Please formalize this as the governing internal-alpha threat-model disposition and update the register accordingly.
> The internal-alpha operating assumption is:
>
> * primary operator is me;
> * a small number of trusted engineers may also be given AEW to experiment with;
> * those users legitimately control their own development accounts/machines;
> * we are defending against model mistakes, confused or unsafe tool use, accidental credential exposure, stale authority and ordinary agent misbehavior;
> * we are NOT designing internal alpha as a hostile multi-tenant environment or against a malicious local engineer.
>
> From that threat model:
>
> 1. Required protection boundary
>
> For internal alpha, model-controlled processes must remain unable to directly mutate canonical AEW/control state or obtain real provider/workflow credentials except through the adopted AEW authority paths.
> Ordinary project files and ordinary user-readable filesystem contents are not required to be isolated as though the model were a hostile remote tenant.
> F18 and F28 provide the important production boundary here. Do not add a broader whole-home-directory isolation requirement merely for internal alpha.
>
> 2. Platform posture
>
> Rocky/Linux is the production-guarantee target for internal alpha.
> Windows/WSL support is valuable for development and testing, but production-equivalent containment on Windows/WSL is NOT an internal-alpha requirement.
> Windows/WSL results must remain truthfully labelled according to their actual guarantees and cannot be used as evidence that the Linux production containment contract was satisfied.
>
> 3. Operator attribution
>
> For internal alpha, attribution to the authenticated/local OS user and AEW operator session is sufficient for consequential operator actions.
> Do not require MFA-style reauthentication, cryptographic signing of every operator decision, or another high-friction confirmation mechanism.
> Operator-only capabilities must still remain structurally unavailable to model-controlled processes as already required.
>
> 4. Lead inactivity expiry
>
> A long-inactivity Lead lease/expiry is desirable hardening but is NOT a prerequisite to internal alpha.
> Track it as a later bounded improvement.
> If implemented, its purpose is abandonment cleanup—for example a Lead attachment left around over a long vacation—not short-session policing. Expiry should stale/revoke the Lead attachment and require fresh attachment/generation under Q12 semantics; it must not silently kill independently admitted child work.
> Do not block alpha on this mechanism.
>
> 5. Two-account OS separation
>
> Do NOT require the entire model harness to run as a separate human-created OS account for internal alpha.
> The adopted F18 protected-state/principal boundary and F28 credential/network custody are the security properties that matter.
> A two-account profile may remain a future stronger deployment option, but it is not an alpha requirement.
>
> 6. Remote delivery
>
> AEW should eventually be allowed to push an already accepted local commit with explicit operator approval.
> For the bounded internal-alpha form, the desired semantics are:
>
> * engineering completion is based on the accepted/verified local result;
> * push is a separate delivery action, not part of correctness or DONE;
> * operator approves the exact push;
> * destination remote/ref is explicit;
> * no force push;
> * AEW records an attributable receipt containing the accepted local commit, requested remote/ref and resulting remote SHA/ref;
> * the pushed remote object must resolve to the exact accepted commit;
> * ordinary exact-commit push does not require a second verification merely because it crossed the network.
>
> A push/network/authentication failure is a delivery failure, not retroactive `VERIFICATION_FAILED`.
>
> 7. PR / provider merge workflow
>
> Automated PR creation and provider-generated merge-commit handling are NOT internal-alpha requirements.
> The target environment may not even make automated PR creation practical.
> Therefore defer Q14's broader PR/merge questions:
>
> * provider-specific PR creation;
> * remote merge workflow;
> * whether a provider-generated merge commit requires a second verification;
> * DONE semantics when a provider merge commit differs from the accepted candidate.
>
> Q14 should no longer block internal alpha. Reopen it when remote PR/merge integration becomes an actual product requirement.
> F23 disposition
> Mark F23 ADOPTED / CLOSED as the internal-alpha threat-model decision.
> The candidate-hardening disposition is:
>
> * F18/F28 canonical-state and credential boundaries: REQUIRED
> * Linux/Rocky production target: REQUIRED
> * trusted-engineer internal-alpha use: ALLOWED
> * Windows/WSL dev/test use with weaker truthful guarantees: ALLOWED
> * local OS/session operator attribution: SUFFICIENT
> * separate full model OS account: NOT REQUIRED
> * Lead inactivity expiry: NICE-TO-HAVE / DEFERRED HARDENING
> * bounded operator-approved exact-commit push: ALLOWED / DESIGN OR IMPLEMENT AS DELIVERY CAPABILITY
> * automated PR/merge-provider integration: DEFERRED
> * Q14 as an internal-alpha gate: REMOVED
>
> Do not turn this into a new broad security architecture exercise. The point of F23 was to decide which candidate controls the actual alpha threat model justifies; most of the stronger candidates are intentionally rejected or deferred.

## 2. Filing (lead developer)

- **Register.** F23 closes. Its candidates are disposed of as the decision says. Two of them become rows of their own:
  - **F33**, the operator-approved exact-commit push, a delivery capability that is not part of `DONE`;
  - **E50**, Lead inactivity expiry, a deferred hardening that cleans up abandoned attachments under Q12's semantics and
    never kills admitted child work.
- **Gates.** The internal-alpha gate gains the requirement this decision names: the F18 and F28 canonical-state and
  credential boundaries, on Rocky/Linux. The F28 network-containment gate is unchanged.
- **Q14.** Q14 stops being an internal-alpha gate and is deferred until remote PR or merge integration is a product
  requirement. The [remote integration target sketch](proposals/remote-integration-target-sketch-2026-10-04.md) stays a
  proposal for that time.
- **Reading, operator confirmation (lead developer).** Item 3 rules out MFA, per-decision signing and other new
  high-friction confirmation. AEW's existing mechanisms are not of that kind, so both stand:
  - **The broker's refusal.** The operator-only commands of #103 (`authority accept` and `reject`, `manifest adopt`,
    `migrate`) are refused in a Lead session by the Lead broker (`OPERATOR_DECIDED`).
  - **The terminal challenge.** A decision recorded as the operator's (`authority accept --decided-by operator`, `work
    staff --by operator`, a takeover) needs a one-time code typed back at the operator's own terminal (`aew.operator`).

  Neither of these is what makes operator-only capabilities "structurally unavailable to model-controlled processes"
  in production. A terminal check is not an absent capability (F18 hosting v0.6 §2.1, §2.3). That property comes from
  F18.6's principal separation, with the operator-only lifecycle socket authorized by peer credentials. Item 3 keeps
  the property and changes none of these mechanisms.
- **Reading, principals (lead developer).** Item 5 removes only the requirement that the whole model harness run as a
  separate *human-created* OS account. The F18 hosting design v0.6 §2.1 to §2.3 stand unamended: canonical state stays
  protected from the Lead-host identity, and the operator-only socket must tell the operator from the harness by peer
  credentials, so a deployment that collapses the two principals is still refused. F18.6 meets this with one of the
  options v0.6 already names: a dedicated OS identity for the harness (§2.1) or an SELinux-confined domain. Only an SELinux domain
  would let the harness keep the operator's own uid. The two-account profile stays an optional stronger deployment.
- **Windows and WSL.** No new mechanism is needed. Runs on these platforms are already labelled by what they actually
  provide (`workdir_separation_only`, `job_object`, `network: not_provided`), and those labels are never evidence for the
  Linux containment contract.
- Ledger prefix IAT.
