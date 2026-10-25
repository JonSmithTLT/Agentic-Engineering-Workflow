"""The G3 confirmer under the host's own Python (STG-03, G3-B): a plain-assert run for Rocky 8's platform-python, 3.6,
which pytest (3.9 and later) and AEW's test helpers (3.11) cannot run on. Its result is recorded in the pull request.

    /usr/libexec/platform-python -I -B tests/helpers/g3_confirm_py36.py G3_DIR RUNTIME_DIR CASES [--pin PIN]

G3_DIR is a copy's ``g3/``; RUNTIME_DIR holds the sockets of a THROWAWAY service that the caller started from that
copy, with its own state directory (never the installed service, and never the operator's PIN); CASES is
``tests/fixtures/g3/g3-cases.json``. Without ``--pin`` it makes no PIN attempt: it lists, shows, declines and checks
the refusals that need none. With ``--pin``, the throwaway service's synthetic PIN, it also approves, sends a wrong
PIN and retries. It imports the window module too, so GTK's import on this Python is part of the proof. With
``GDK_BACKEND=broadway`` and a private ``broadwayd`` (never a desktop's display), it also drives the real window: it
lists, selects, shows every row and declines through it, and with ``--pin`` approves through its PIN field.
"""

import json
import os
import secrets
import sys


def main(argv):
    g3_dir, runtime_dir, cases_file = argv[:3]
    pin = argv[argv.index("--pin") + 1] if "--pin" in argv else None
    sys.path.insert(0, g3_dir)
    from aew_g3_confirm import core, window  # the window's import (GTK on this Python) is proven too

    confirm = os.path.join(runtime_dir, "confirm.sock")
    request = os.path.join(runtime_dir, "request.sock")
    with open(cases_file, "rb") as f:
        p1 = json.loads(f.read().decode("utf-8"))["cases"]["P1"]

    def ask():
        cs = json.loads(json.dumps(p1["approval_request"]["command_set"]))
        cs["request_set_ref"] = "request:py36-" + secrets.token_hex(4)
        for intent in cs["intents"]:
            intent["origin_proof_ref"] = "proof:" + secrets.token_hex(16)
        body = json.dumps({"wire_version": core.WIRE, "command_set": cs}).encode("utf-8")
        status, out = core._call(request, "POST", "/g3/v1/approval-requests", body)
        assert status == 201, (status, out)
        return out["approval_ref"]

    done = []
    print("python", sys.version.split()[0], "| gtk", window.Gtk.get_major_version(), window.Gtk.get_minor_version())
    assert sys.version_info[:2] == (3, 6), sys.version
    assert window.main(["--pin", "123456"]) == 2  # refused before any window or request (G3-05)
    done.append("an argument is refused: exit 2")

    ref = ask()
    listed = core.list_pending(confirm)
    assert ref in [core.summary(p)[0] for p in listed]
    shown = core.rows(next(p for p in listed if core.summary(p)[0] == ref))
    assert len(shown) == len(next(p for p in listed if core.summary(p)[0] == ref)["rendering"])
    done.append("list and show: " + str(len(shown)) + " rows")
    assert core.decide(ref, None, confirm) == core.DECLINED
    assert core.decide(ref, None, confirm) == "NOT_FOUND"
    done.append("decline, then NOT_FOUND")
    try:
        core.list_pending(os.path.join(runtime_dir, "absent.sock"))
        raise AssertionError("no socket, yet an answer")
    except core.Unreachable:
        done.append("no service: Unreachable")
    if pin is not None:
        ref = ask()
        assert core.decide(ref, "py36-wrong-" + secrets.token_hex(3), confirm) == "PIN_INCORRECT"
        assert core.decide(ref, pin, confirm) == core.APPROVED
        assert core.decide(ref, pin, confirm) == "NOT_FOUND"
        done.append("wrong PIN, approve, retry NOT_FOUND")
    if os.environ.get("GDK_BACKEND") == "broadway":  # a private broadwayd: the window is built, never on a screen
        done += drive_window(window, core, confirm, ask, pin)
    for line in done:
        print("ok:", line)
    print("PY36-CONFIRMER-CHECKS PASS")
    return 0


def drive_window(window, core, confirm, ask, pin):
    """The real window, on broadway: it lists, shows every row of the selected approval, and declines (and, with the
    throwaway PIN, approves through the PIN field, which it empties as the decision leaves)."""
    import time

    gtk = window.Gtk

    def pump(until, what):
        deadline = time.monotonic() + 15
        while not until():
            while gtk.events_pending():
                gtk.main_iteration_do(False)
            assert time.monotonic() < deadline, "the window never got to: " + what
            time.sleep(0.02)

    said = []
    app = window.Confirmer(confirm)
    app.window.show_all()
    for decision in ["DECLINE"] + (["APPROVE"] if pin is not None else []):
        ref = ask()
        app._refresh()
        pump(lambda ref=ref: ref in [row[0] for row in app.approvals], "listing " + ref)
        index = [row[0] for row in app.approvals].index(ref)
        app.listing.get_selection().select_path(gtk.TreePath(index))
        expected = len(core.rows(next(p for p in app.pending if core.summary(p)[0] == ref)))
        pump(lambda expected=expected: len(app.lines) == expected, "showing " + str(expected) + " rows")
        assert app.approve.get_sensitive() and app.decline.get_sensitive()
        if decision == "DECLINE":
            app.decline.clicked()
            pump(lambda: core.MESSAGES[core.DECLINED] in app.status.get_text(), "declining")
        else:
            app.pin.set_text(pin)
            app.approve.clicked()
            assert app.pin.get_text() == "", "the PIN left the field as the decision left"
            pump(lambda: core.MESSAGES[core.APPROVED] in app.status.get_text(), "approving")
        said.append("window: " + decision.lower() + " through the window, " + str(expected) + " rows shown")
    return said


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
