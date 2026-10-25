"""The confirmer's window (A-37 G3-03, G3-05; STG-03, G3-B; addendum 4): GTK3, through the host's own
``python3-gobject``.

The only module that imports GTK, so no CI test opens a window; the run under the host's Python drives it on a private
broadway display (``tests/helpers/g3_confirm_py36.py``). It takes the PIN only from its own entry field, typed on its
own window; never from its arguments, its environment, standard input or any IPC (G3-05). Each decision is sent once,
from a worker thread, with every button held until the reply; nothing refreshes the list while it is in flight. The PIN
field is cleared as a decision leaves, whenever the shown approval changes, and when the window closes (#282, m1).

One instance per desktop session (``Gtk.Application``). Started at login it has no window: it polls the pending list
and posts one notification per pending approval, in fixed text and with no decision on it. The window is shown only
by the operator's own act, a launch from the menu or a click on a notification, and only in ``App.present``: nothing
the poll does opens, raises or focuses it (addendum 4).
"""

import signal
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

import gi  # pyright: ignore[reportMissingImports] - the host's python3-gobject, absent from CI

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402  # pyright: ignore[reportMissingImports] - after require_version

from . import core  # noqa: E402 - after GTK's version is pinned, as PyGObject requires

TITLE = "AEW approvals"


def _in_background(call: Callable[[], Any], done: Callable[[Any, Optional[Exception]], None]) -> None:
    def work() -> None:
        result = None  # type: Any
        error = None  # type: Optional[Exception]
        try:
            result = call()
        except Exception as e:  # any failure is shown as no answer; core's texts never hold the PIN
            error = e
        GLib.idle_add(lambda: done(result, error) and False)

    threading.Thread(target=work, daemon=True).start()


class Confirmer:
    def __init__(self, sock_path: str = core.CONFIRM_SOCK) -> None:
        self.sock_path = sock_path
        self.pending = []  # type: List[Dict[str, Any]]
        self.current = None  # type: Optional[Dict[str, Any]]
        self.deciding = False
        self.window = Gtk.Window(title=TITLE)
        self.window.set_default_size(980, 720)

        self.approvals = Gtk.ListStore(str, str)  # approval_ref, expires_at
        self.listing = Gtk.TreeView(model=self.approvals)
        for i, title in enumerate(("Approval", "Expires at")):
            self.listing.append_column(Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i))
        self.listing.get_selection().connect("changed", self._on_select)

        self.lines = Gtk.ListStore(str, str)  # label, value
        shown = Gtk.TreeView(model=self.lines)
        for i, title in enumerate(("Field", "Value")):
            cell = Gtk.CellRendererText(family="Monospace")
            shown.append_column(Gtk.TreeViewColumn(title, cell, text=i))
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.add(shown)

        self.pin = Gtk.Entry(visibility=False, input_purpose=Gtk.InputPurpose.PIN, placeholder_text="PIN")
        self.pin.connect("activate", lambda _w: self._approve())
        self.approve = Gtk.Button(label="Approve")
        self.approve.connect("clicked", lambda _w: self._approve())
        self.decline = Gtk.Button(label="Decline")
        self.decline.connect("clicked", lambda _w: self._decline())
        self.refresh = Gtk.Button(label="Refresh")
        self.refresh.connect("clicked", lambda _w: self._refresh())
        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)

        controls = Gtk.Box(spacing=8)
        for w in (self.pin, self.approve, self.decline, self.refresh):
            controls.pack_start(w, False, False, 0)
        top = Gtk.ScrolledWindow()
        top.set_min_content_height(120)
        top.add(self.listing)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=12)
        for w, grow in ((top, False), (scroll, True), (controls, False), (self.status, False)):
            box.pack_start(w, grow, grow, 0)
        self.window.add(box)
        self._show(None)

    # ------------------------------------------------------------------------------------------ the list
    def _refresh(self, notice: str = "") -> None:
        """Lists the open approvals again; ``notice``, a decision's outcome, stays shown above what the list says."""
        self._busy(True)
        _in_background(lambda: core.list_pending(self.sock_path),
                       lambda result, error: self._listed(result, error, notice))

    def _listed(self, result: Any, error: Optional[Exception], notice: str) -> None:
        self.pending = result if error is None else []
        self.approvals.clear()
        for p in self.pending:
            self.approvals.append(list(core.summary(p)))
        self.current = None
        self._busy(False)
        said = [notice] if notice else []
        if error is not None:
            said.append(core.list_failure(error))  # a refusal's own text, or that there was no answer (#282, m2)
        elif not self.pending:
            said.append("No approval is pending.")
        self.status.set_text("\n".join(said))

    def _on_select(self, selection: Any) -> None:
        model, it = selection.get_selected()
        ref = model[it][0] if it is not None else None
        self._show(next((p for p in self.pending if core.summary(p)[0] == ref), None))

    def _show(self, pending: Optional[Dict[str, Any]]) -> None:
        self.pin.set_text("")  # a PIN typed for one approval never stays for another (#282, m1)
        self.current = pending
        self.lines.clear()
        approvable = False
        if pending is not None:
            try:
                for label, value in core.rows(pending):
                    self.lines.append([label, value])
                approvable = True
                self.status.set_text("")
            except core.Malformed as e:
                self.lines.clear()
                self.status.set_text("This approval cannot be shown exactly (" + str(e) + "), so it can only be "
                                     "declined.")
        self.approve.set_sensitive(approvable)
        self.pin.set_sensitive(approvable)
        self.decline.set_sensitive(pending is not None)

    # ------------------------------------------------------------------------------------------ deciding
    def _approve(self) -> None:
        if self.current is None or not self.approve.get_sensitive():
            return
        pin = self.pin.get_text()
        self.pin.set_text("")  # the PIN leaves the field as the decision leaves
        self._decide(pin)

    def _decline(self) -> None:
        if self.current is not None:
            self._decide(None)

    def _decide(self, pin: Optional[str]) -> None:
        ref = core.summary(self.current or {})[0]
        self.deciding = True
        self._busy(True)
        _in_background(lambda: core.decide(ref, pin, self.sock_path), self._decided)

    def _decided(self, outcome: Any, error: Optional[Exception]) -> None:
        # Every outcome refreshes the list: a decided, lost or expired approval leaves it (addendum 2 §1).
        self.deciding = False
        self._refresh(core.decision_failure(error) if error is not None else core.message(outcome))

    # ------------------------------------------------------------------------------------------ plumbing
    def _busy(self, busy: bool) -> None:
        for w in (self.approve, self.decline, self.refresh, self.pin, self.listing):
            w.set_sensitive(not busy)
        if not busy:
            self._show(self.current)


class App:
    """The one instance in a desktop session: the window when the operator asks for it, and the notifications."""

    def __init__(self, at_login: bool, sock_path: str = core.CONFIRM_SOCK) -> None:
        self.at_login = at_login
        self.sock_path = sock_path
        self.confirmer = None  # type: Optional[Confirmer]
        self.watch = core.Watch()
        self.polling = False
        self.started = False
        self.app = Gtk.Application(application_id=core.APP_ID)
        self.app.connect("activate", self._on_activate)
        self.app.connect("shutdown", self._on_shutdown)
        show = Gio.SimpleAction.new("show", None)  # a notification's click: the operator's own act
        show.connect("activate", lambda _a, _p: self.present())
        self.app.add_action(show)
        self.notification = Gio.Notification.new(core.NOTIFY_TITLE)
        self.notification.set_body(core.NOTIFY_BODY)
        self.notification.set_default_action("app.show")  # no buttons: a decision is made only in the window

    def _on_activate(self, _app: Any) -> None:
        if not self.started:
            self.started = True
            self.app.hold()  # alive with no window; the window's close hides it, or quits a menu-started instance
            self._poll()
            GLib.timeout_add_seconds(core.POLL_S, self._poll)
            if self.at_login:
                return
        self.present()

    def present(self) -> None:
        """The only place the window is shown, raised or focused: a launch from the menu, or a notification's click."""
        if self.confirmer is None:
            self.confirmer = Confirmer(self.sock_path)
            self.confirmer.window.connect("delete-event", self._on_close)
        self.confirmer.window.show_all()
        self.confirmer.window.present()
        if not self.confirmer.deciding:  # a decision in flight refreshes the list itself, on its reply (#282, n3)
            self.confirmer._refresh()

    def _on_close(self, window: Any, _event: Any) -> bool:
        if self.confirmer is not None:
            self.confirmer.pin.set_text("")  # a closed window keeps no PIN (#282, m1)
        window.hide()
        if not self.at_login:
            self.app.quit()
        return True

    def _on_shutdown(self, _app: Any) -> None:
        """An ending instance withdraws what it posted, so no notification outlives the instance that would withdraw
        it (#282 review, m3): a desktop may keep an exited application's notifications, even across a logout."""
        for ref in sorted(self.watch.posted):
            self.app.withdraw_notification(core.notification_id(ref))
        self.watch.posted = set()
        bus = self.app.get_dbus_connection()
        if bus is not None:
            bus.flush_sync(None)  # the withdrawals leave before the process does

    def run(self) -> int:
        """Runs the instance until it quits. SIGTERM and SIGHUP, as at a logout, quit it the same way, through
        ``shutdown``, so its notifications are withdrawn first (#282 review, m3)."""
        if sys.platform != "win32":  # G3 is a Linux profile; this narrows SIGHUP for the type checker
            for signum in (signal.SIGTERM, signal.SIGHUP):
                GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signum, self._on_signal)
        return self.app.run([sys.argv[0]])

    def _on_signal(self) -> bool:
        self.app.quit()
        return False  # once is enough

    # ------------------------------------------------------------------------------------------ the notifications
    def _poll(self) -> bool:
        if not self.polling:  # a read still in flight (up to TIMEOUT_S) is waited for, never doubled
            self.polling = True
            _in_background(lambda: core.list_pending(self.sock_path), self._polled)
        return True  # the timer keeps running

    def _polled(self, result: Any, error: Optional[Exception]) -> None:
        self.polling = False
        if isinstance(error, core.NotPermitted) and self.at_login and self.confirmer is None:
            self.app.quit()  # another account's login: it exits, with no window, notification or message
            return
        if error is not None:
            return  # the service is down or stalled: it degrades quietly, and the next poll tries again
        post, withdraw = self.watch.update(result)
        for ref in post:  # with no notification service, GLib drops these; nothing fails and no dialog appears
            self.app.send_notification(core.notification_id(ref), self.notification)
        for ref in withdraw:
            self.app.withdraw_notification(core.notification_id(ref))


def main(argv: List[str]) -> int:
    """Starts the confirmer, from ``start.main``, which has checked the arguments before GTK was imported."""
    if not core.arguments_ok(argv):
        return 2
    at_login = argv == [core.AT_LOGIN]
    if at_login and not core.may_use():
        return 0  # another account's login: the socket is the operator's (addendum 4)
    GLib.set_application_name(TITLE)
    app = App(at_login)
    try:
        app.app.register(None)
    except GLib.Error:
        if at_login:
            return 0  # no session bus: nothing to notify through, and nothing fails
        raise
    if at_login and app.app.get_is_remote():
        return 0  # one instance per session: a second login start never activates, so never opens, the first
    return app.run()
