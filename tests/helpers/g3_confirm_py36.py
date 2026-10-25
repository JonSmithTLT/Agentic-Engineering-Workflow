"""The G3 confirmer under the host's own Python (STG-03, G3-B): a plain-assert run for Rocky 8's platform-python, 3.6,
which pytest (3.9 and later) and AEW's test helpers (3.11) cannot run on. Its result is recorded in the pull request.

    /usr/libexec/platform-python -I -B tests/helpers/g3_confirm_py36.py G3_DIR RUNTIME_DIR CASES [--pin PIN]

G3_DIR is a copy's ``g3/``; RUNTIME_DIR holds the sockets of a THROWAWAY service that the caller started from that
copy, with its own state directory (never the installed service, and never the operator's PIN); CASES is
``tests/fixtures/g3/g3-cases.json``. Without ``--pin`` it makes no PIN attempt: it lists, shows, declines and checks
the refusals that need none. With ``--pin``, the throwaway service's synthetic PIN, it also approves, sends a wrong
PIN and retries. It imports the window module too, so GTK's import on this Python is part of the proof. With
``GDK_BACKEND=broadway`` and a private ``broadwayd``, or ``GDK_BACKEND=x11`` and a private ``Xvnc`` (never a desktop's
display), it also drives the real window: it lists, selects, shows every row and declines through it, and with
``--pin`` approves through its PIN field. Under ``dbus-run-session`` it also drives the notifications (addendum 4).
"""

import json
import os
import secrets
import subprocess
import sys


def child(g3_dir, confirm, entry):
    """A child interpreter as the launcher runs one (``-I -B``), at the throwaway's socket: ``core.CONFIRM_SOCK`` is
    set before the window module is imported, so its defaults, and so even an ablated build, never reach the
    installed service. ``entry`` is ``start`` (the launcher's entry) or ``app`` (an instance started at login)."""
    run = (f"import sys; sys.path.insert(0, {g3_dir!r}); from aew_g3_confirm import core; "
           f"core.CONFIRM_SOCK = {confirm!r}; ")
    if entry == "start":
        run += "from aew_g3_confirm.start import main; sys.exit(main(sys.argv[1:]))"
    else:
        run += ("from aew_g3_confirm import window; a = window.App(True); a.app.register(None); "
                "sys.exit(a.run())")
    return [sys.executable, "-I", "-B", "-c", run]


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
    for extra in (["--pin", "123456"], ["--name=x", core.AT_LOGIN], ["--class=y", "--g-fatal-warnings"]):
        # As the launcher starts it, with GTK's own options too, which GTK would take out of sys.argv at import (m5)
        p = subprocess.run(child(g3_dir, confirm, "start") + extra, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=30)
        assert p.returncode == 2 and "takes no arguments" in p.stderr, (extra, p.returncode, p.stderr)
    done.append("an argument is refused before GTK is imported, GTK's own options too: exit 2")

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
    if os.environ.get("GDK_BACKEND") in ("broadway", "x11"):  # a private broadwayd or Xvnc, never a screen
        done += drive_window(window, core, confirm, ask, pin)
        if os.environ.get("DBUS_SESSION_BUS_ADDRESS", "").startswith("unix:"):  # a private bus from dbus-run-session
            done += drive_app(window, core, g3_dir, confirm, ask)
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
            app.pin.set_text("typed-then-declined")
            app.decline.clicked()
            pump(lambda: core.MESSAGES[core.DECLINED] in app.status.get_text(), "declining")
            assert app.pin.get_text() == "", "a PIN typed before a Decline stayed in the field (m1)"
        else:
            app.pin.set_text(pin)
            app.approve.clicked()
            assert app.pin.get_text() == "", "the PIN left the field as the decision left"
            pump(lambda: core.MESSAGES[core.APPROVED] in app.status.get_text(), "approving")
        said.append("window: " + decision.lower() + " through the window, " + str(expected) + " rows shown")

    first, second = ask(), ask()  # m1: a PIN typed for one approval is gone once another is selected
    app._refresh()
    pump(lambda: {first, second} <= {row[0] for row in app.approvals}, "listing two")
    refs = [row[0] for row in app.approvals]
    app.listing.get_selection().select_path(gtk.TreePath(refs.index(first)))
    pump(lambda: app.current is not None and core.summary(app.current)[0] == first, "selecting the first")
    app.pin.set_text("typed-for-the-first")
    app.listing.get_selection().select_path(gtk.TreePath(refs.index(second)))
    pump(lambda: core.summary(app.current or {})[0] == second, "selecting the second")
    assert app.pin.get_text() == "", "a PIN typed for one approval stayed for another (m1)"
    for ref in (first, second):
        assert core.decide(ref, None, confirm) == core.DECLINED
    said.append("window: a re-selection empties the PIN field")

    os.chmod(confirm, 0)  # m2: a refused list says so in its own words, not "did not answer"
    try:
        app._refresh()
        pump(lambda: core.LIST_MESSAGES["PEER_NOT_PERMITTED"] in app.status.get_text(), "the refusal's own text")
        assert core.LIST_UNREACHABLE not in app.status.get_text()
    finally:
        os.chmod(confirm, 0o600)
    said.append("window: a refused list shows the refusal's own text")
    app.window.destroy()
    return said


NOTIFICATIONS = """<node><interface name="org.freedesktop.Notifications">
<method name="Notify"><arg type="s" direction="in"/><arg type="u" direction="in"/><arg type="s" direction="in"/>
<arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="as" direction="in"/>
<arg type="a{sv}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="out"/></method>
<method name="CloseNotification"><arg type="u" direction="in"/></method>
<method name="GetCapabilities"><arg type="as" direction="out"/></method>
<method name="GetServerInformation"><arg type="s" direction="out"/><arg type="s" direction="out"/>
<arg type="s" direction="out"/><arg type="s" direction="out"/></method>
<signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
<signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
</interface></node>"""
# Every call that opens, raises or focuses a window (tests/unit/test_g3_confirm.py, SHOWS, as GTK names them).
SHOWS = {"Widget": ("show", "show_all", "show_now", "grab_focus"),
         "Window": ("present", "present_with_time", "deiconify", "set_keep_above", "set_urgency_hint", "set_focus",
                    "maximize", "fullscreen", "stick")}


def drive_app(window, core, g3_dir, confirm, ask):
    """Addendum 4, on a private session bus with a stand-in notification service (GTK's freedesktop backend): the
    login start shows no window and posts one fixed-text notification per pending approval, once, and withdraws it when
    the approval is decided; a poll never opens, raises or focuses a window, with the window closed or open; a click
    opens it; a menu launch opens the running instance's window, and a second login start does nothing; with no
    notification service nothing fails; on another account's socket the login start quits with nothing shown; and an
    instance sent SIGTERM withdraws what it posted."""
    import signal
    import time

    gio, glib, gtk = window.Gio, window.GLib, window.Gtk
    calls, ids, said = [], [0], []

    def on_call(conn, sender, path, iface, method, params, invocation):
        calls.append((method, params.unpack()))
        if method == "Notify":
            ids[0] += 1
            invocation.return_value(glib.Variant("(u)", (ids[0],)))
        elif method == "GetCapabilities":
            invocation.return_value(glib.Variant("(as)", (["actions", "body"],)))
        elif method == "GetServerInformation":
            invocation.return_value(glib.Variant("(ssss)", ("stand-in", "aew", "0", "1.2")))
        else:
            invocation.return_value(None)

    def pump(until, what, secs=15):
        deadline = time.monotonic() + secs
        while not until():
            glib.MainContext.default().iteration(False)
            assert time.monotonic() < deadline, "never got to: " + what
            time.sleep(0.01)

    def poll(app):
        app._poll()
        pump(lambda: not app.polling, "a poll's end")
        for _ in range(20):  # GLib's notification calls are asynchronous: let them reach the bus
            glib.MainContext.default().iteration(False)
            time.sleep(0.01)

    def notifies():
        return [c[1] for c in calls if c[0] == "Notify"]

    shows = []

    def counted(real, name):
        def call(self, *a):
            shows.append(name)
            return real(self, *a)
        return call

    for cls, names in SHOWS.items():
        for name in names:
            setattr(getattr(gtk, cls), name, counted(getattr(getattr(gtk, cls), name), name))

    bus = gio.bus_get_sync(gio.BusType.SESSION, None)
    iface = gio.DBusNodeInfo.new_for_xml(NOTIFICATIONS).interfaces[0]
    bus.register_object("/org/freedesktop/Notifications", iface, on_call, None, None)
    owned = []
    owner = gio.bus_own_name_on_connection(bus, "org.freedesktop.Notifications", gio.BusNameOwnerFlags.NONE,
                                           lambda *a: owned.append(1), None)
    pump(lambda: owned, "owning the notification service's name")

    # m3: an instance that ends withdraws what it posted; SIGTERM, as at a logout, quits it through its shutdown.
    ended = subprocess.Popen(child(g3_dir, confirm, "app"), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             universal_newlines=True)
    try:
        early = ask()
        pump(lambda: notifies(), "the login instance's notification", 30)
        ended.send_signal(signal.SIGTERM)
        pump(lambda: ended.poll() is not None, "the instance's exit on SIGTERM", 30)
        pump(lambda: any(c[0] == "CloseNotification" for c in calls), "the withdrawal as it ended")
    finally:
        if ended.poll() is None:
            ended.kill()
    assert ended.returncode == 0, (ended.returncode, ended.stderr.read())
    assert core.decide(early, None, confirm) == core.DECLINED
    del calls[:]
    said.append("SIGTERM: the instance quits, and withdraws what it posted")

    app = window.App(True, confirm)
    app.app.register(None)
    assert not app.app.get_is_remote()
    app._on_activate(app.app)  # the login start
    ref = ask()
    poll(app)
    pump(lambda: notifies(), "a notification")
    sent = notifies()
    assert len(sent) == 1 and sent[0][3:6] == (core.NOTIFY_TITLE, core.NOTIFY_BODY, ["default", ""]), sent
    poll(app)
    poll(app)
    assert len(notifies()) == 1, "a later poll repeated it"
    assert app.confirmer is None and shows == [], shows
    said.append("login start: no window; one notification, fixed text, no buttons; not repeated")

    assert core.decide(ref, None, confirm) == core.DECLINED
    poll(app)
    pump(lambda: any(c[0] == "CloseNotification" for c in calls), "the withdrawal")
    said.append("decided: withdrawn")

    run = child(g3_dir, confirm, "start")
    second = subprocess.Popen(run + [core.AT_LOGIN], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pump(lambda: second.poll() is not None, "a second login start's exit", 30)
    assert second.returncode == 0 and app.confirmer is None and shows == [], (second.returncode, shows)
    said.append("a second login start: exit 0, nothing opened")

    ask()
    poll(app)
    pump(lambda: len(notifies()) == 2, "the next approval's notification")
    bus.emit_signal(None, "/org/freedesktop/Notifications", "org.freedesktop.Notifications", "ActionInvoked",
                    glib.Variant("(us)", (ids[0], "default")))  # the operator's click
    pump(lambda: app.confirmer is not None and app.confirmer.window.get_visible(), "the window, on the click")
    assert {"show_all", "present"} <= set(shows)
    said.append("a click opens the window")
    del shows[:]
    ask()
    poll(app)
    pump(lambda: len(notifies()) == 3, "a notification with the window open")
    assert shows == [], shows
    said.append("with the window open: notified, and the window not raised or focused")

    app.confirmer.pin.set_text("typed-then-closed")  # m1: a closed window keeps no PIN
    app._on_close(app.confirmer.window, None)
    assert app.confirmer.pin.get_text() == "" and not app.confirmer.window.get_visible(), "a PIN outlived the close"
    said.append("closing the window empties the PIN field")
    app.confirmer.deciding = True  # n3: as with a decision in flight, whose reply is still to come
    app.confirmer._busy(True)
    menu = subprocess.Popen(run, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pump(lambda: menu.poll() is not None and app.confirmer.window.get_visible(), "the menu launch's window", 30)
    assert menu.returncode == 0 and "present" in shows
    said.append("a menu launch opens the running instance's window")
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:  # long enough for a refresh's reply to have released the buttons
        glib.MainContext.default().iteration(False)
        time.sleep(0.01)
    held = (app.confirmer.refresh, app.confirmer.listing, app.confirmer.approve, app.confirmer.decline)
    assert not any(w.get_sensitive() for w in held), \
        "opening the window released the buttons while a decision was in flight (n3)"
    app.confirmer.deciding = False
    app.confirmer._busy(False)
    said.append("a decision in flight keeps every button held when the window is opened")

    gio.bus_unown_name(owner)
    toplevels = len(gtk.Window.list_toplevels())
    del shows[:]
    ask()
    poll(app)
    poll(app)
    assert len(notifies()) == 3 and len(gtk.Window.list_toplevels()) == toplevels and shows == []
    said.append("no notification service: nothing fails, no dialog")

    os.chmod(confirm, 0)  # as another account sees the operator's 0600 socket
    try:
        other = window.App(True, confirm)
        quits = []
        other.app.quit = lambda: quits.append(1)
        other._on_activate(other.app)
        pump(lambda: quits, "another account's login start quitting")
        assert other.confirmer is None and len(notifies()) == 3 and shows == []
    finally:
        os.chmod(confirm, 0o600)
        other.polling = True  # its timer's later polls stay idle: it stands for an instance that has quit
    said.append("another account: quits, with nothing shown")
    return said


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
