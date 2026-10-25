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
- **The tests:** `tests/unit/test_g3_rules.py`, `tests/unit/test_g3_facts.py` and
  `tests/integration/test_g3_process.py`. The regression aid's binding cases run against the real service.

**Next in the stage:** G3-B (the confirmer) and G3-D (the CLI client). G3-C (the owners' side) waits only for this
`consume`. G3 is not established on any host until CS-4 contains the Lead (G3-12).
