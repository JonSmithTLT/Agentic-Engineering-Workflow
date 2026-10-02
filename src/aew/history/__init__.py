"""Cold history (ADR-0011): the immutable records of finished work, an append-only manifest that pins them by hash,
and a derived lookup index.

- ``manifest``: entries, the hash chain over them (plan R1), and the bounded files they live in.
- ``store``: reading, appending (inside a control-store transaction), verifying and pre-writing records.
- ``index``: the rebuildable SQLite lookup index under ``local/``.

Nothing here decides what is archived or when (that is the engine's transaction finalizer, plan R6); it keeps
whatever it is given immutable, ordered and verifiable.
"""
