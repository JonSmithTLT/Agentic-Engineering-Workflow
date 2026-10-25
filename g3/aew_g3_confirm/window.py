"""The confirmer's window (A-37 G3-03, G3-05; STG-03, G3-B): GTK3, through the host's own ``python3-gobject``.

The only module that imports GTK, so no CI test opens a window; the run under the host's Python drives it on a private
broadway display (``tests/helpers/g3_confirm_py36.py``). It takes the PIN only from its own entry field, typed on
its own window; never from its arguments, its environment, standard input or any IPC (G3-05). Each decision is sent
once, from a worker thread, with every button held until the reply; the PIN field is cleared as the decision leaves.
"""

import sys
import threading
from typing import Any, Callable, Dict, List, Optional

import gi  # pyright: ignore[reportMissingImports] - the host's python3-gobject, absent from CI

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402  # pyright: ignore[reportMissingImports] - after require_version

from . import core  # noqa: E402 - after GTK's version is pinned, as PyGObject requires

TITLE = "AEW approvals"


class Confirmer:
    def __init__(self, sock_path: str = core.CONFIRM_SOCK) -> None:
        self.sock_path = sock_path
        self.pending = []  # type: List[Dict[str, Any]]
        self.current = None  # type: Optional[Dict[str, Any]]
        self.window = Gtk.Window(title=TITLE)
        self.window.set_default_size(980, 720)
        self.window.connect("destroy", Gtk.main_quit)

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
        self._in_background(lambda: core.list_pending(self.sock_path),
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
            said.append(core.UNREACHABLE)
        elif not self.pending:
            said.append("No approval is pending.")
        self.status.set_text("\n".join(said))

    def _on_select(self, selection: Any) -> None:
        model, it = selection.get_selected()
        ref = model[it][0] if it is not None else None
        self._show(next((p for p in self.pending if core.summary(p)[0] == ref), None))

    def _show(self, pending: Optional[Dict[str, Any]]) -> None:
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
        self._busy(True)
        self._in_background(lambda: core.decide(ref, pin, self.sock_path), self._decided)

    def _decided(self, outcome: Any, error: Optional[Exception]) -> None:
        # Every outcome refreshes the list: a decided, lost or expired approval leaves it (addendum 2 §1).
        self._refresh(core.UNREACHABLE if error is not None else core.message(outcome))

    # ------------------------------------------------------------------------------------------ plumbing
    def _busy(self, busy: bool) -> None:
        for w in (self.approve, self.decline, self.refresh, self.pin, self.listing):
            w.set_sensitive(not busy)
        if not busy:
            self._show(self.current)

    def _in_background(self, call: Callable[[], Any], done: Callable[[Any, Optional[Exception]], None]) -> None:
        def work() -> None:
            result = None  # type: Any
            error = None  # type: Optional[Exception]
            try:
                result = call()
            except Exception as e:  # any failure is shown as no answer; core's texts never hold the PIN
                error = e
            GLib.idle_add(lambda: done(result, error) and False)

        threading.Thread(target=work, daemon=True).start()


def main(argv: List[str]) -> int:
    """Takes no arguments: nothing reaches the confirmer but the operator's own typing (G3-05)."""
    if argv:
        sys.stderr.write("aew-g3-confirm takes no arguments: the PIN is typed into its window only\n")
        return 2
    app = Confirmer()
    app.window.show_all()
    app._refresh()
    Gtk.main()
    return 0
