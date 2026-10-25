# The G3 service (STG-03)

G3 is AEW's one operator origin for a protected action. The rules are A-37, G3 revision 7.1, in the architecture
workspace. The wire is A-26's `g3-wire.schema.json` (`g3-0.6.1-candidate`), vendored here byte for byte. The order of
an approval:

1. A client (the CLI or the website backend) submits the exact command set, and gets a pending approval back.
2. The operator approves it with a PIN, in a confirmer window outside every sandbox.
3. The service issues a signed consent record, bound to the exact set and short-lived.
4. The owner consumes the record once, at allocation.
5. If anything fails, the action is held.

This directory is part G3-A: the service and its systemd units. The confirmer (G3-B), the owners' side (G3-C) and the
CLI client (G3-D) come next.

## What runs, and as whom

| Piece | Where | Who |
|---|---|---|
| `aew_g3` (this package) | `/opt/aew-g3/aew_g3`, root-owned | the service, as its own dynamic account (`DynamicUser=yes`), with no capabilities |
| The venv: Python 3.11 with `cryptography`, `jsonschema` and `aew` (non-editable) | `/opt/aew-g3/venv`, root-owned, bytecode compiled at install | the same |
| The deployment values | `/opt/aew-g3/etc/deployment.json`, root's | read once, at start |
| The key, the PIN's hash, the ledger | `/var/lib/aew-g3` (`StateDirectory=`), mode 0600 | the service's account alone |
| `request.sock`, `confirm.sock` | `/run/aew-g3/`, from `aew-g3.socket` | the operator's account only (`SocketUser=`, mode 0600, and a UID check on every request) |
| The public keys and `issuer_ref` | `/run/aew-g3/keys/`, mode 0644 | anyone, for audit |

The operator's editable `aew` install never runs any of it. The service takes three things from `aew`, the sealed
O-01 command schema, the action registry, and SW-02's canonical bytes and set digest, so it derives them from their
one owner instead of copying them. It also takes AEW's typed errors. A test pins that list.

## The toolchain, and why

- **Python 3.11,** from Rocky 8's AppStream (`python3.11`). The native-executable rule and the install manifest were
  cut in A-37. Python lets the service derive O-01 and SW-02 from `aew.stg02`, instead of carrying a second
  implementation of the digest it must agree with byte for byte.
- **`cryptography`** for the P-256 ECDSA key (G3-09): the standard library has no ECDSA. It is used with its defaults.
- **SQLite** for the durable ledger, with `synchronous=FULL` and one `BEGIN IMMEDIATE` transaction per write. Primary
  keys make each proof and each consumed member unique.
- **`hashlib.scrypt`** for the PIN's hash, and **`http.server`** over the Unix sockets, with `SO_PEERCRED` for the
  caller's UID. Both are standard library.
- **Offline:** `requirements-offline.txt` pins every wheel by hash (SPT's py311 wheelhouse). `install.sh` installs
  with `--no-index --require-hashes`.

## Install (root, on the host)

```sh
sudo sh g3/install.sh --operator <account> --wheelhouse <dir> --aew-wheel <aew-*.whl>
sudo /usr/local/sbin/aew-g3 set-pin
```

The full path, because Rocky 8's `sudo` searches only its `secure_path`, which leaves out `/usr/local/sbin`.

`install.sh` enables both units, so the service comes back after a reboot. A reinstall keeps the PIN, the key, the
ledger and `etc/deployment.json`, and says so; set the PIN only after the first install.

- `set-pin` reads the PIN twice from the terminal. It stores only a salted scrypt hash, and the minimum length the PIN
  was set under. Setting the PIN also ends a lockout.
- `sudo /usr/local/sbin/aew-g3 rotate-key`, then a restart of `aew-g3.service`, retires the signing key. A record
  signed under the retired key stays verifiable from its published public key, and is no longer consumable.

## Tests

- **`tests/unit/test_g3_rules.py`:** the regression aid's binding cases (A-26's `g3-cases.json`, vendored in
  `tests/fixtures/g3/`) and the planted controls, run in process on both platforms.
- **`tests/unit/test_g3_facts.py`:** the deployment's tripwires, the PIN's bounds, the key, the issuer and the wire.
  It also checks that the units, `install.sh` and the code name the same sockets, directories and install root. The
  `g3` extra must pin the same `cryptography` as `requirements-offline.txt`. The service may load from `aew` only the
  allowed modules, read both from the source and at run time. Every refusal reason the code names must be planted by
  some G3 test.
- **`tests/unit/test_g3_admin.py`:** `set-pin` and `rotate-key` as root runs them, on Linux, with `os.geteuid` patched
  and `getpass` stubbed. Every file either command writes must be handed to the state directory's owner. It also
  covers the refusals of administration and start, and the peer's UID read unsigned.
- **`tests/integration/test_g3_process.py`:** the real process on its real sockets, on Linux. It covers socket
  activation, refusals to start, a restart after `SIGKILL`, a race between consumers, and a planted PIN that never
  appears. It also checks the peer check on every request, including those http.server refuses itself, and that a
  refusal waits for the declared body. A stalled client is dropped at the request timeout. Bodies at and over
  `MAX_BODY`, a PIN that is not UTF-8 and a body nested past the parser are each held to their rule.

**Coverage:** the coverage ratchet measures `src/aew` only, so it does not count this package's lines.
