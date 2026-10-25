**G3-A, the G3 service and its units (2026-10-25), built from A-37 (G3 revision 7.1) and the designer's hand-off
addenda 1 to 3.** The service is in a new top-level directory, `g3/`, apart from the editable `aew` install. Root
installs it under `/opt/aew-g3` with `g3/install.sh`, offline, every wheel pinned by hash. What it is:
- **The account:** `DynamicUser=yes`, with no capabilities.
- **The sockets:** `request.sock` and `confirm.sock` under `/run/aew-g3/`, from `aew-g3.socket`, with a UID check on
  every request.
- **The durable state:** a P-256 key file, the PIN's salted scrypt hash, and an SQLite ledger with `synchronous=FULL`.
- **The rules:** G3-02 to G3-08 in their order; G3-11's holds; G3-14's four tripwires, checked at start and never
  clamped.
- **The toolchain:** Python 3.11, with `cryptography` for P-256. The service imports from `aew` only the sealed O-01
  files, SW-02 and the typed errors, so it derives them from their one owner.
- **The tests:** `tests/unit/test_g3_rules.py`, `tests/unit/test_g3_facts.py`, `tests/unit/test_g3_admin.py` and
  `tests/integration/test_g3_process.py`. The regression aid's binding cases run against the real service.
- **Root's commands:** the full path `/usr/local/sbin/aew-g3`, since sudo on Rocky 8 searches only its `secure_path`.
  Whatever `set-pin` or `rotate-key` writes as root is handed to the service's account, because systemd's
  `StateDirectory=` set-up does not descend to fix it (review of #269, M1).
- **The server:** a request's declared body is read before any reply, so a refused client still receives its
  refusal. A stalled client is dropped after 30 s. http.server's own refusals pass the peer check and carry the wire's
  Problem (review of #269, M2 and m1).

**Follow-up, SPT's wheelhouse (2026-10-25):** SPT's py311 wheelhouse carries only `cryptography` 47.0.0, below G3's
pin of 50.0.2 (47.0.0 has published advisories: PYSEC-2026-3552, fixed in 50.0.0; PYSEC-2026-3553 and -3554, fixed
in 49.0.0; GHSA-537c-gmf6-5ccf, fixed in 48.0.1). **A precondition:** G3 on the operator's work machine, and the
operator's trial there, wait for SPT's py311 wheelhouse to carry `cryptography` 50.0.2. Packages there come from SPT's
wheelhouse, and no personal device may bring one in. Carrying PyPI's
`cryptography-50.0.2-cp311-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` by hand, checked against the hash in
`g3/requirements-offline.txt`, is a route only for hosts that allow it, such as the test VM. What fixes it: an SPT
change that adds `cryptography` 50.0.2 to its py311 wheelhouse.
Its `Requires-Dist` (`cffi>=2.0.0`; `cffi` 2.0.0 takes any `pycparser`) moves nothing else SPT already carries.

**Next in the stage:** G3-B (the confirmer) and G3-D (the CLI client). G3-C (the owners' side) waits only for this
`consume`. G3 is not established on any host until CS-4 contains the Lead (G3-12).
