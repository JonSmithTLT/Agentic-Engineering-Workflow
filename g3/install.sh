#!/bin/sh
# Installs AEW's G3 service and its confirmer (A-37, G3-14) root-owned under /opt/aew-g3, and enables the service's
# units. Root runs it, offline, from a checkout's g3/ directory:
#
#   sudo sh g3/install.sh --operator <account> --wheelhouse <dir> --aew-wheel <aew-*.whl>
#
#   --operator    the operator's account: it alone may connect to the sockets (SocketUser=, G3-10)
#   --wheelhouse  a directory holding the wheels requirements-offline.txt pins by hash
#   --aew-wheel   a wheel of aew built from the same commit as this checkout (pip wheel --no-deps .)
#
# Nothing under /opt/aew-g3 is writable by the operator or by the service's own dynamic account; the bytecode is
# compiled here, as root, and the service runs with -B. An existing etc/deployment.json is kept: changing it is root's
# administration (G3-14). Afterwards root sets the PIN: sudo /usr/local/sbin/aew-g3 set-pin
# (the full path: Rocky 8's sudo secure_path does not include /usr/local/sbin, and /usr/sbin is the package manager's)
set -eu

ROOT=/opt/aew-g3
UNITS=/etc/systemd/system
WRAPPER=/usr/local/sbin/aew-g3
PIN_RECORD=/var/lib/aew-g3/pin.json  # StateDirectory=aew-g3, the PIN's record (pinstore.PIN_FILE)
# The confirmer (G3-B) runs on the operator's desktop under the host's own Python 3 and its GTK3 bindings. Its two
# desktop entries are named for its application id (core.APP_ID), as the desktop's notifications require.
CONFIRM=/opt/aew-g3/bin/aew-g3-confirm
CONFIRM_LINK=/usr/local/bin/aew-g3-confirm
CONFIRM_PY=/usr/libexec/platform-python
DESKTOP=/usr/share/applications/org.aew.G3Confirm.desktop
AUTOSTART=/etc/xdg/autostart/org.aew.G3Confirm.desktop
HERE=$(cd "$(dirname "$0")" && pwd)
OPERATOR= WHEELHOUSE= AEW_WHEEL=
while [ $# -gt 0 ]; do
    case "$1" in
        --operator) OPERATOR=$2; shift 2 ;;
        --wheelhouse) WHEELHOUSE=$2; shift 2 ;;
        --aew-wheel) AEW_WHEEL=$2; shift 2 ;;
        *) echo "install.sh: unknown argument $1" >&2; exit 2 ;;
    esac
done
fail() { echo "install.sh: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || fail "run it as root (sudo): the install is root's (G3-14)"
[ -n "$OPERATOR" ] && [ -n "$WHEELHOUSE" ] && [ -n "$AEW_WHEEL" ] || fail "--operator, --wheelhouse and --aew-wheel are required"
uid=$(id -u "$OPERATOR") || fail "no account named $OPERATOR"
[ "$uid" != 0 ] || fail "the operator is never root (G3-01)"
[ -d "$WHEELHOUSE" ] || fail "no wheelhouse at $WHEELHOUSE"
[ -f "$AEW_WHEEL" ] || fail "no aew wheel at $AEW_WHEEL"
PY=$(command -v python3.11) || fail "python3.11 is not installed (Rocky 8: dnf install python3.11)"
[ -f /etc/machine-id ] || fail "/etc/machine-id is missing: the service derives its issuer_ref from it"

umask 022
"$PY" -m venv --clear "$ROOT/venv"
"$ROOT/venv/bin/python" -m pip install --quiet --no-index --no-compile --require-hashes \
    --find-links "$WHEELHOUSE" -r "$HERE/requirements-offline.txt"
"$ROOT/venv/bin/python" -m pip install --quiet --no-index --no-compile --no-deps "$AEW_WHEEL"
rm -rf "$ROOT/aew_g3" "$ROOT/aew_g3_confirm"
mkdir -p "$ROOT/aew_g3" "$ROOT/aew_g3_confirm" "$ROOT/etc" "$ROOT/bin"
cp "$HERE"/aew_g3/*.py "$HERE"/aew_g3/*.json "$ROOT/aew_g3/"
cp "$HERE"/aew_g3_confirm/*.py "$ROOT/aew_g3_confirm/"
if [ -e "$ROOT/etc/deployment.json" ]; then
    echo "install.sh: keeping the existing $ROOT/etc/deployment.json"
else
    cp "$HERE/etc/deployment.json" "$ROOT/etc/deployment.json"
fi
# The service imports aew_g3 from the install root: -I ignores PYTHONPATH, and this .pth is root's.
site=$("$ROOT/venv/bin/python" -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
echo "$ROOT" > "$site/aew-g3.pth"
"$ROOT/venv/bin/python" -I -m compileall -q "$ROOT/aew_g3" "$site"
if [ -x "$CONFIRM_PY" ]; then
    "$CONFIRM_PY" -I -m compileall -q "$ROOT/aew_g3_confirm"
fi
chown -R root:root "$ROOT"
chmod -R go-w "$ROOT"

sed "s/@OPERATOR@/$OPERATOR/" "$HERE/systemd/aew-g3.socket" > "$UNITS/aew-g3.socket"
cp "$HERE/systemd/aew-g3.service" "$UNITS/aew-g3.service"
chmod 0644 "$UNITS/aew-g3.socket" "$UNITS/aew-g3.service"
cat > "$WRAPPER" <<EOF
#!/bin/sh
exec $ROOT/venv/bin/python -I -B -m aew_g3 "\$@"
EOF
chmod 0755 "$WRAPPER"
# The confirmer reads no PIN from anywhere but its own window (G3-05): its one argument is the autostart entry's start
# mode. -I keeps PYTHONPATH and the user's site out, and the install root is put on the path here, root's.
cat > "$CONFIRM" <<EOF
#!/bin/sh
exec $CONFIRM_PY -I -B -c 'import sys; sys.path.insert(0, "$ROOT"); from aew_g3_confirm.start import main; sys.exit(main(sys.argv[1:]))' "\$@"
EOF
chmod 0755 "$CONFIRM"
ln -sfn "$CONFIRM" "$CONFIRM_LINK"  # for a terminal; both desktop entries name the pinned path itself
# The desktop reads its entries from its own directories, as systemd reads the units from $UNITS: root's, holding no
# code and no values, naming only the pinned path (addendum 4). The autostart entry starts it with no window at every
# desktop login; on another account's, it exits at once.
cp "$HERE/desktop/org.aew.G3Confirm.desktop" "$DESKTOP"
mkdir -p "$(dirname "$AUTOSTART")"
cp "$HERE/desktop/autostart/org.aew.G3Confirm.desktop" "$AUTOSTART"
chmod 0644 "$DESKTOP" "$AUTOSTART"
if command -v restorecon >/dev/null 2>&1; then
    restorecon -R "$ROOT" "$UNITS/aew-g3.socket" "$UNITS/aew-g3.service" "$WRAPPER" "$CONFIRM_LINK" "$DESKTOP" \
        "$AUTOSTART"
fi
systemctl daemon-reload
systemctl enable --now aew-g3.socket
# The service starts at boot too, not only at its first connection: its public keys are published, and a deployment
# value it refuses shows at boot rather than at the operator's first approval.
systemctl enable aew-g3.service
systemctl restart aew-g3.service
systemctl --no-pager --lines=5 status aew-g3.service || true
# A reinstall never touches the service's state, so a PIN set before is kept.
if [ -e "$PIN_RECORD" ]; then
    echo "install.sh: installed. The PIN set before is kept."
else
    echo "install.sh: installed. Set the PIN: sudo $WRAPPER set-pin"
fi
if [ -x "$CONFIRM_PY" ] && "$CONFIRM_PY" -I -c 'import gi; gi.require_version("Gtk", "3.0")' 2>/dev/null; then
    echo "install.sh: the operator approves in the confirmer: AEW approvals among the desktop's applications, or" \
         "$CONFIRM_LINK. From their next login it also notifies them when an approval is waiting."
else
    echo "install.sh: the confirmer needs $CONFIRM_PY with GTK3 (Rocky 8: dnf install gtk3 python3-gobject);" \
         "approvals wait until both are installed" >&2
fi
