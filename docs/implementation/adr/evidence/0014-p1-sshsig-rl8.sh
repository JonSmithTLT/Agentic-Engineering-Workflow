#!/usr/bin/bash
# ADR-0014 probes P1 and P2 on the Rocky 8 reference host: does the base OpenSSH verify sshsig signatures, and does
# Python 3.11's tarfile carry the extraction filters? Output is the ADR's evidence (no host names, no user names).
set -u
echo "== host =="
cat /etc/rocky-release
ssh -V 2>&1
rpm -q openssh python3.11 openssl gnupg2 tar 2>&1
echo "== P1: sshsig in the base OpenSSH =="
d=$(mktemp -d); cd "$d" || exit 1
ssh-keygen -q -t ed25519 -N "" -C "aew-release-probe" -f k
printf '{"schema": "aew/bundle-manifest/v1"}\n' > m.json
ssh-keygen -Y sign -f k -n aew-bundle m.json > sign.out 2>&1; echo "ssh-keygen -Y sign: exit $? ($(head -1 sign.out))"
printf 'release@aew namespaces="aew-bundle" %s\n' "$(cut -d' ' -f1,2 k.pub)" > allowed
ssh-keygen -Y verify -f allowed -I release@aew -n aew-bundle -s m.json.sig < m.json > verify.out 2>&1; echo "ssh-keygen -Y verify: exit $? ($(head -1 verify.out))"
ssh-keygen -Y check-novalidate -n aew-bundle -s m.json.sig < m.json > check.out 2>&1; echo "ssh-keygen -Y check-novalidate: exit $? ($(head -1 check.out))"
ssh-keygen -lf k.pub | cut -d' ' -f1,2,4
echo "== P2: tarfile extraction filters in python3.11 =="
python3.11 - <<'PY'
import io, sys, tarfile, tempfile
print("python", sys.version.split()[0], "tarfile.data_filter:", hasattr(tarfile, "data_filter"))
def archive(name, **kw):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        ti = tarfile.TarInfo(name)
        for k, v in kw.items():
            setattr(ti, k, v)
        if ti.type == tarfile.REGTYPE:
            ti.size = 1
            t.addfile(ti, io.BytesIO(b"x"))
        else:
            t.addfile(ti)
    buf.seek(0)
    return buf
cases = {"traversal ../evil": dict(name="../evil"), "absolute /etc/evil": dict(name="/etc/evil"),
         "symlink to /etc/passwd": dict(name="l", type=tarfile.SYMTYPE, linkname="/etc/passwd"),
         "hardlink to ../../x": dict(name="h", type=tarfile.LNKTYPE, linkname="../../x"),
         "fifo": dict(name="f", type=tarfile.FIFOTYPE), "char device": dict(name="c", type=tarfile.CHRTYPE),
         "setuid mode 4755": dict(name="s", mode=0o4755)}
for label, kw in cases.items():
    name = kw.pop("name")
    with tarfile.open(fileobj=archive(name, **kw)) as t, tempfile.TemporaryDirectory() as out:
        try:
            t.extractall(out, filter="data")
            import os
            got = [(p, oct(os.lstat(os.path.join(out, p)).st_mode & 0o7777)) for p in os.listdir(out)]
            print(f"{label}: EXTRACTED {got}")
        except tarfile.FilterError as e:
            print(f"{label}: refused by the data filter ({type(e).__name__})")
PY
cd / && rm -rf "$d"
