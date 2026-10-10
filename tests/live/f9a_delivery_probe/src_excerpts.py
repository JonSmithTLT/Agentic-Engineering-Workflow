"""Write the pinned binary's embedded source around the delivery-relevant definitions (read-only inspection).

Usage: src_excerpts.py BINARY OUT. The header names the binary by its version and sha256 only, never by its path, so
the output can be committed as evidence (``src-excerpts.txt``).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

PICKS = [  # (label, anchor, bytes before, bytes after)
    ("Session.prompt: reconcile by id, admit, wake unless resume is false", b'se=u("Session.prompt")', 0, 900),
    ("SessionInbox.reconcile: an existing id in the same session and of the same type is returned as is",
     b'class jt extends z()("SessionInbox.LifecycleConflict"', 0, 400),
    ("SessionInbox.reconcile/admit", b'DE=u("SessionInbox.make")', 0, 900),
    ("nextPromotable / promote: steer items first; queue items one at a time", b'm9=u("SessionInbox.nextPromotable")',
     0, 2100),
    ("SessionRunner.drain: between steps only steer is promoted; queue only when the loop would complete",
     b'f=u("SessionRunner.drain")', 0, 2600),
    ("Errors: PromptConflictError, BusyError", b'class Ls extends z()("Session.PromptConflictError"', 200, 500),
    ("HTTP errors: ConflictError 409", b'class iA extends z()("ConflictError"', 0, 250),
    ("Interrupt with resume: steering input resumes, queued prompts stay parked",
     b"interrupt:(p,k)=>A(function*(){let g=yield*D.interrupt", 0, 400),
    ("Shell tool: default foreground timeout 120000 ms, 0 disables", b'var Wd="shell",gy=120000', 0, 200),
    ("Shell tool: timeout applied, 'Command exceeded timeout'",
     b"execute:(N,O)=>A(function*(){let V=N.background===!0?N.timeout??0:N.timeout??gy", 0, 900),
    ("Session.background: explicit request only", b'background:u("Session.background")', 0, 700),
]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    data = Path(sys.argv[1]).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as out:
        out.write(f"# Excerpts from the OpenCode CLI binary, version 2.0.18 (sha256 {digest}); "
                  "byte offsets in the binary\n\n")
        for label, anchor, before, after in PICKS:
            i = data.find(anchor)
            out.write(f"## {label}\n@{i}\n")
            out.write((data[max(0, i - before): i + after].decode("utf-8", "replace") if i >= 0 else "NOT FOUND")
                      + "\n\n")


if __name__ == "__main__":
    main()
