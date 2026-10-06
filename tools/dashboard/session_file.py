#!/usr/bin/env python3
"""Exchange a dashboard one-time URL for the browser runner's private session file (register F20.6).

    aew dashboard open                       # at your terminal: prints the one-time URL there
    python tools/dashboard/session_file.py <out.json>     # then paste the URL on standard input

The URL is read from standard input, never from the command line (a process listing would show it). The tool
follows it as a browser's address bar does (a top-level navigation), takes the ``aew_session`` cookie from the
``303``, checks it reads ``/api/v1/project``, and writes the web side's session file
(``web/docs/reference/f20-live-browser-handoff.md``)::

    {"version": 1, "origin": "http://127.0.0.1:4280", "cookie": {"name": "aew_session", "value": "aew1.<id>.<secret>"}}

The file is created owner-only: mode 0600 on POSIX; on Windows its inherited ACL is replaced by one granting only
the current user. Keep it in a private scratch directory, never in evidence, and delete it after the run; the
session dies with the server anyway. The tool prints the origin and the file's path, never the credential.
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
    """Create ``path`` readable by its owner only, then write ``text``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    if os.name == "nt":  # replace the inherited ACL before any secret is written
        user = os.environ.get("USERNAME") or ""
        domain = os.environ.get("USERDOMAIN") or ""
        who = f"{domain}\\{user}" if domain else user
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{who}:(R,W)"], check=True,
                       capture_output=True, creationflags=NO_WINDOW)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


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
