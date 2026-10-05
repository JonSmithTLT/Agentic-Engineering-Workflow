"""The read-only dashboard's server side (register F20.2 to F20.6; the design note
``docs/design/proposals/dashboard-main-line-api-design-v0.1.md``).

It serves contract 0.1.2 (``docs/design/dashboard-api-v1-provisional.yaml``) over stdlib ``http.server``: GET and
HEAD, same-origin, bound to ``127.0.0.1`` only. It reads the committed control state **lock-free**
(``ControlStore.read_committed``, ADR-0012 D3) and projects it field by field from an allowlist, so no storage path,
run directory, verifier or credential ever leaves the server. It changes no engineering state.

**Enablement rule (designer, 2026-10-05):** no merged state ever serves project data unauthenticated.
``DashboardServer`` requires an authenticator; the product's one is the operator session (F20.3, ``session.py``): a
credential of the kind ``operator_session`` minted after the operator's typed-back code at a terminal, delivered once
as a one-time URL, held as an ``HttpOnly`` cookie, verified by the engine's own lookup over the server's in-memory
table, and dead when the server stops. ``aew dashboard serve|open|status`` (``cli/dashboard_commands.py``) are the
only way to start one; ``service.py`` ties the table, the HTTP server and the local control channel (``control.py``)
together.
"""
