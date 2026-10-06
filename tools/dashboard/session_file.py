#!/usr/bin/env python3
"""Exchange a dashboard one-time URL for the browser runner's private session file (register F20.6).

    aew dashboard open                       # at your terminal: prints the one-time URL there
    python tools/dashboard/session_file.py <out.json>     # then paste the URL on standard input

The URL is read from standard input, never from the command line (a process listing would show it). The tool
follows it as a browser's address bar does (a top-level navigation), takes the ``aew_session`` cookie from the
``303``, checks it reads ``/api/v1/project``, and writes the web side's session file
(``web/docs/reference/f20-live-browser-handoff.md``)::

    {"version": 1, "origin": "http://127.0.0.1:4280", "cookie": {"name": "aew_session", "value": "aew1.<id>.<secret>"}}

The file is created owner-only and written through its creating handle: mode 0600 on POSIX; on Windows a protected
DACL granting only the current user's SID, set at creation. Keep it in a private scratch directory, never in
evidence, and delete it after the run; the session dies with the server anyway. The tool prints the origin and the
file's path, never the credential.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
import sys
from pathlib import Path

URL = re.compile(r"^(http://127\.0\.0\.1:(\d+))(/session/[A-Za-z0-9_-]{20,128})$")
COOKIE = "aew_session"
NAVIGATION = {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def exchange(url: str) -> tuple[str, str]:
    """The origin and the session credential a one-time URL is exchanged for."""
    m = URL.match(url.strip())
    if not m:
        raise SystemExit("not a dashboard one-time URL (http://127.0.0.1:<port>/session/<code>)")
    origin, port, path = m.group(1), int(m.group(2)), m.group(3)
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        conn.request("GET", path, headers=NAVIGATION)
        resp = conn.getresponse()
        resp.read()
        if resp.status != 303:
            raise SystemExit(f"the server answered {resp.status}: the link was used, expired, or never issued; run "
                             "`aew dashboard open` for a new one")
        set_cookie = resp.getheader("Set-Cookie") or ""
    finally:
        conn.close()
    first = set_cookie.split(";", 1)[0]
    if not first.startswith(f"{COOKIE}=aew1."):
        raise SystemExit("the exchange set no session cookie")
    value = first[len(COOKIE) + 1:]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        conn.request("GET", "/api/v1/project", headers={"Cookie": f"{COOKIE}={value}", "Sec-Fetch-Site": "same-origin"})
        resp = conn.getresponse()
        resp.read()
        if resp.status != 200:
            raise SystemExit(f"the new session does not read the API ({resp.status})")
    finally:
        conn.close()
    return origin, value


def write_private(path: Path, text: str) -> None:
    """Create ``path`` readable by its owner only and write ``text`` through the creating handle.

    The file never exists with wider access, and is never reopened by name (a swap between the two would let the
    secret land elsewhere): on POSIX ``O_CREAT | O_EXCL`` with mode 0600; on Windows ``CreateFileW`` with a protected
    security descriptor granting only the current user's SID full access, opened without sharing. Any failure leaves
    no file and nothing written (PR #97 review A1-A4: an ACL narrowed after creation by display name could be read
    in between, could fail on a localized or renamed account, and kept the runner's default-DACL entries)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    fd = _create_owner_only_nt(path) if os.name == "nt" else os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def user_sid() -> str:
    """The current user's SID (``whoami /user``): only its ASCII SID column is read, so the account's display name,
    language and code page never matter."""
    out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True,
                         creationflags=NO_WINDOW).stdout.decode("ascii", "replace")
    sid = out.strip().rsplit(",", 1)[-1].strip().strip('"')
    if not re.fullmatch(r"S-1-\d+(-\d+)+", sid):
        raise SystemExit("could not read the current user's SID; no session file written")
    return sid


def _create_owner_only_nt(path: Path) -> int:  # pragma: windows-only
    """A new file whose DACL is protected (nothing inherited) and grants only the current user, created that way in
    one call, with no sharing; returns a writable file descriptor."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                    ("bInheritHandle", wintypes.BOOL)]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    to_sd = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    to_sd.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    to_sd.restype = wintypes.BOOL
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(SecurityAttributes),
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    sd = ctypes.c_void_p()
    if not to_sd(f"D:P(A;;FA;;;{user_sid()})", 1, ctypes.byref(sd), None):  # SDDL_REVISION_1
        raise OSError(ctypes.get_last_error(), "could not build the session file's security descriptor")
    try:
        attrs = SecurityAttributes(ctypes.sizeof(SecurityAttributes), sd, False)
        generic_write, no_sharing, create_new, normal = 0x40000000, 0, 1, 0x80
        handle = create(str(path), generic_write, no_sharing, ctypes.byref(attrs), create_new, normal, None)
    finally:
        kernel.LocalFree(sd)
    if handle is None or handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), f"could not create {path} owner-only")
    try:
        return msvcrt.open_osfhandle(handle, os.O_WRONLY)
    except BaseException:  # the handle is still ours: close it, so the file can go (PR #97 re-review B1)
        kernel.CloseHandle(handle)
        path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: session_file.py <out.json>   (the one-time URL on standard input)")
    out = Path(args[0])
    origin, value = exchange(sys.stdin.readline())
    record = {"version": 1, "origin": origin, "cookie": {"name": COOKIE, "value": value}}
    write_private(out, json.dumps(record) + "\n")
    print(f"session file for {origin} written to {out} (owner-only; delete it after the run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
