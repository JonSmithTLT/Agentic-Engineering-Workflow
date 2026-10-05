"""The read-only dashboard's server side (register F20.2 to F20.6; the design note
``docs/design/proposals/dashboard-main-line-api-design-v0.1.md``).

It serves contract 0.1.2 (``docs/design/dashboard-api-v1-provisional.yaml``) over stdlib ``http.server``: GET and
HEAD, same-origin, bound to ``127.0.0.1`` only. It reads the committed control state **lock-free**
(``ControlStore.read_committed``, ADR-0012 D3) and projects it field by field from an allowlist, so no storage path,
run directory, verifier or credential ever leaves the server. It changes no engineering state.

**Enablement rule (designer, 2026-10-05):** no merged state ever serves project data unauthenticated. F20.2 lands the
reader, the projections and the server class, and nothing that listens outside a test: ``DashboardServer`` requires
an authenticator, the only one in the product arrives with F20.3 (the operator-session credential), and the
``aew dashboard`` commands arrive with it.
"""
