**The certificate route after the relay's pre-UAT change, 2026-11-27** (`fix/relay-hardening-before-uat`, STG-05's note
of the same day). The relay now removes a credential from a failed answer's body before it reaches the run. A request on
the certificate route carries no credential, so its answers stream as before, untouched; a test keeps its request going
with no key (`test_the_certificate_routes_request_carries_no_key_and_still_goes`). How OpenCode backs off on a 429 is
still unmeasured: it stays SYS-47's first live check, on the operator's preflight for the UAT (STG-05's note).
