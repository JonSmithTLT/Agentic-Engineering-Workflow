#!/bin/sh
# Installs AEW's G3 service (A-37, G3-14) root-owned under /opt/aew-g3 and enables its socket. Root runs it, offline,
# from a checkout's g3/ directory:
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
rm -rf "$ROOT/aew_g3"
mkdir -p "$ROOT/aew_g3" "$ROOT/etc"
cp "$HERE"/aew_g3/*.py "$HERE"/aew_g3/*.json "$ROOT/aew_g3/"
if [ -e "$ROOT/etc/deployment.json" ]; then
    echo "install.sh: keeping the existing $ROOT/etc/deployment.json"
else
    cp "$HERE/etc/deployment.json" "$ROOT/etc/deployment.json"
fi
# The service imports aew_g3 from the install root: -I ignores PYTHONPATH, and this .pth is root's.
site=$("$ROOT/venv/bin/python" -I -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
echo "$ROOT" > "$site/aew-g3.pth"
"$ROOT/venv/bin/python" -I -m compileall -q "$ROOT/aew_g3" "$site"
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
if command -v restorecon >/dev/null 2>&1; then
    restorecon -R "$ROOT" "$UNITS/aew-g3.socket" "$UNITS/aew-g3.service" "$WRAPPER"
fi
systemctl daemon-reload
systemctl enable --now aew-g3.socket
systemctl restart aew-g3.service
systemctl --no-pager --lines=5 status aew-g3.service || true
echo "install.sh: installed. Set the PIN: sudo $WRAPPER set-pin"
