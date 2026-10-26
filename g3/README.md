# The G3 service (STG-03)

G3 is AEW's one operator origin for a protected action. The rules are A-37, G3 revision 7.1, in the architecture
workspace. The wire is A-26's `g3-wire.schema.json` (`g3-0.6.1-candidate`), vendored here byte for byte. The order of
an approval:

1. A client (the CLI or the website backend) submits the exact command set, and gets a pending approval back.
2. The operator approves it with a PIN, in a confirmer window outside every sandbox.
3. The service issues a signed consent record, bound to the exact set and short-lived.
4. The owner consumes the record once, at allocation.
5. If anything fails, the action is held.

This directory holds part G3-A, the service and its systemd units, and part G3-B, the confirmer. The owners' side
(G3-C) and the CLI client (G3-D) come next.

## What runs, and as whom

| Piece | Where | Who |
|---|---|---|
| `aew_g3` (this package) | `/opt/aew-g3/aew_g3`, root-owned | the service, as its own dynamic account (`DynamicUser=yes`), with no capabilities |
| The venv: Python 3.11 with `cryptography`, `jsonschema` and `aew` (non-editable) | `/opt/aew-g3/venv`, root-owned, bytecode compiled at install | the same |
| The deployment values | `/opt/aew-g3/etc/deployment.json`, root's | read once, at start |
| The key, the PIN's hash, the ledger | `/var/lib/aew-g3` (`StateDirectory=`), mode 0600 | the service's account alone |
| `request.sock`, `confirm.sock` | `/run/aew-g3/`, from `aew-g3.socket` | the operator's account only (`SocketUser=`, mode 0600, and a UID check on every request) |
| The public keys and `issuer_ref` | `/run/aew-g3/keys/`, mode 0644 | anyone, for audit |
| `aew_g3_confirm`, the confirmer | `/opt/aew-g3/aew_g3_confirm` and its launcher `/opt/aew-g3/bin/aew-g3-confirm`, root-owned; started at login by `/etc/xdg/autostart/org.aew.G3Confirm.desktop`, and from the menu entry "AEW approvals" | the operator, on their own desktop, outside any sandbox |

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
- **Offline:** `requirements-offline.txt` pins every wheel by hash: SPT's py311 wheelhouse's, except `cryptography`
  50.0.2. SPT carries only 47.0.0, which has published advisories, so that wheel comes from PyPI by its hash and is
  carried by hand until SPT has it (the register, STG-03). `install.sh` installs with `--no-index --require-hashes`.

## The confirmer (G3-B)

The window where the operator approves or declines (A-37 G3-03, G3-05). It lists the pending approvals on
`confirm.sock`, and shows the selected one's rendering, one row per served line: a template line shows its
`template_id`, a typed field its `field_path` and its value as JSON, an owner fact its owner, fact, observation and
values. Every value is escaped to ASCII, so no control, bidirectional or look-alike character can disguise it. A
rendering it cannot show exactly can only be declined. The PIN comes only from the window's own entry field: the
confirmer takes no argument but the autostart entry's `--at-login`, and reads nothing from its environment, standard
input or any IPC. Each decision is sent once; after any outcome, the list is refreshed, and the outcome is told in
fixed text, never text the service sent.

**How it reaches the operator** (the designer's addendum 4):
- **It starts at login,** with no window, from a root-owned entry in `/etc/xdg/autostart/`. There is one instance
  per desktop session, and a launch from the menu opens that instance's window.
- **It notifies:** it reads the pending list every 5 seconds, and posts one notification per pending approval through
  the desktop's notification service. The notification is in fixed text, with no rendering line and no decision on it,
  and is withdrawn when the approval leaves the list. A click on it opens the window.
- **It never opens, raises or focuses itself.** The poll touches only the notifications, never the window or its
  list, so an approval arriving never moves the operator's selection or a half-typed PIN. Under xrdp, which is X11, a
  window could take focus, so this is the confirmer's own rule.
- **It degrades quietly:** with no notification service, or the G3 service down, nothing fails and no dialog appears.
  A limit: an approval polled while no notification service is up is not notified when one appears later; the next
  approval is, and the window lists both.
- **An ending instance withdraws its notifications,** when it quits or is sent SIGTERM or SIGHUP, as at a logout, so
  no notification outlives the instance that would withdraw it. One the desktop restores after a crash may stay until
  dismissed.
- **On another account's login** the entry runs too. That account cannot use `confirm.sock`, so the confirmer exits
  at once, silently.
- **The operator can turn it off** for themselves: a file `~/.config/autostart/org.aew.G3Confirm.desktop` holding
  `[Desktop Entry]` and `Hidden=true` overrides the system's entry (the XDG autostart rule), or their desktop's startup
  settings where it has them. The menu still works.
- **The service** logs a successful pending read no more, so the polling does not bury the journal. A refused or failed
  read is logged, as is every other request.

- **The toolkit:** GTK3, through the host's own Python 3 and `python3-gobject` (Rocky 8: `/usr/libexec/platform-python`,
  Python 3.6). The confirmer uses the standard library and GTK only, never `aew` or `aew_g3`, so the facts it restates
  (the socket, the wire's header and version, the rendering's line limit, the Problem codes, root's command) are held
  to their owners by a test.
- **Launching it:** from "AEW approvals" among the desktop's applications, a notification's click, or
  `/usr/local/bin/aew-g3-confirm`. Both desktop entries are named for its application id, `org.aew.G3Confirm`, as
  the desktop's notifications require, and run `/opt/aew-g3/bin/aew-g3-confirm`. It needs an X11 or Wayland session
  of the operator's own. If the host lacks GTK3 for that Python, `install.sh` says
  so, and approvals wait until root installs `gtk3` and `python3-gobject`.

## Install (root, on the host)

```sh
sudo sh g3/install.sh --operator <account> --wheelhouse <dir> --aew-wheel <aew-*.whl>
sudo /usr/local/sbin/aew-g3 set-pin
```

The full path, because Rocky 8's `sudo` searches only its `secure_path`, which leaves out `/usr/local/sbin`.

`install.sh` enables both units, so the service comes back after a reboot. A reinstall keeps the PIN, the key, the
ledger and `etc/deployment.json`, and says so; set the PIN only after the first install. It also installs the
confirmer, its launcher, its menu entry and its autostart entry, and checks that the host's Python can load GTK3 for
it. The confirmer starts by itself from the operator's next login.

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
- **`tests/unit/test_g3_confirm.py`:** the confirmer's restated facts against their owners, what it shows of each kind
  of line, the renderings it refuses whole, the decisions it sends, and the outcome texts. For the notifications: one
  per approval, never repeated, withdrawn when it leaves the list, in fixed text; the desktop entries; and that only
  one method shows the window, reached only by a launch or a click. Two static checks keep it within Python 3.6: the
  parser at its lowest version, and a list of the later names the parser cannot see.
- **`tests/integration/test_g3_confirm_process.py`:** the confirmer's core against the real service, on Linux: listing,
  approving once, declining, every refusal it can draw, another account's socket, the service's log of pending reads,
  and a service that does not answer or is not G3's.
- **`tests/helpers/g3_confirm_py36.py`:** the run under the host's own Python 3.6, which CI does not have, against a
  throwaway service. On a private broadway display and a private session bus, it also drives the real window and the
  notifications, through a stand-in notification service. Its result is recorded in the pull request.

**Coverage:** the coverage ratchet measures `src/aew` only, so it does not count this package's lines.
