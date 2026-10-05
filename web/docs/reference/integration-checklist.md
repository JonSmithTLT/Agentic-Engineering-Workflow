# Live integration checklist

This is current frontend handoff guidance, not evidence of completed backend integration. The [original core checklist](../archive/core/integration-checklist.md) remains historical.

- Confirm the accepted API/capability/authentication contract, project bootstrap, session handling and refusal semantics before connecting production.
- Main-line owners supply packaging/static serving, Host/Origin policy, CSP/security headers and the actual session cookie. Fixture servers do not prove those behaviors.
- Exercise the compiled production build against the live server with explicit target/session inputs once the integration interface exists; keep fixtures distinct from live acceptance.
- Accept immutable snapshot retention, reference association authorization, exact artifact/range/digest semantics and excerpt policy before W05 adoption.
- Accept source/snapshot ownership, context accounting, packet authorization and receipt guarantees before W04 adoption.
- Accept T3 event/outbox design and an explicit projection adapter before W06 adoption; settle typed relationship meanings and accepted control vocabulary. Adapt G7/F7 budgets rather than adopting fixture fields.
- Reconcile upcoming Knowledge Capture & Admission projections through explicit contracts; preserve canonical Evidence identity and browser non-inference.
- Re-run production exclusion, hostile-content, scope/validator isolation and UI task checks on the integrated system. Record backend adoption and frontend fixture acceptance independently.

Open questions are maintained in [milestone ledgers](backend-questions/README.md). This checklist creates no Engine records or commitments.
