"""The launch self-test's judgement (STG-05 CB-12, rows 2 to 5), on synthetic probe output.

Pure: nothing starts bubblewrap, so it runs on every platform. The rows on a real sandbox, and each failing closed when
a protection is taken out, are in tests/integration/test_containment.py. Row 4 is judged here, and on a real sandbox
by the pseudo-terminal launcher test there. Row 2's socket inventory (the designer's D-CS2-2 to D-CS2-5) is judged
here on synthetic host inventories and synthetic probe output, and the probe's own matching on synthetic mount tables.
"""

from __future__ import annotations

import errno
import stat
from types import SimpleNamespace

import pytest

from aew.harness import containment as C
from aew.harness.containment import layout as L
from aew.harness.containment import probe, sockets

LAYOUT = L.Layout(role="reviewer", access="read", bwrap="/usr/bin/bwrap", writable=("/runs/R-1/scratch",),
                  readonly=(), hide_runs=("/runs",), hide_host=("/run",), run_exceptions=())
INVENTORY = {  # the host's side (sockets.inventory): what the table held, classified
    "control": True, "table": 40, "seconds": 0.01,
    "candidates": [{"path": "/var/lib/sss/pipes/nss", "listed": "/var/lib/sss/pipes/nss", "class": sockets.REPORTED,
                    "dev": 2050, "ino": 7, "majmin": "8:2", "fspath": "/var/lib/sss/pipes/nss"},
                   {"path": "/home/u/.cache/cm/master", "listed": "/home/u/.cache/cm/master.Xy12",
                    "class": sockets.CREDENTIAL, "dev": 2050, "ino": 8, "majmin": "8:2",
                    "fspath": "/u/.cache/cm/master"}],
    "abstract": [{"name": "@/tmp/.X11-unix/X0", "class": sockets.DISPLAY}],
    "relative": [{"name": "relative.sock", "class": sockets.REPORTED}],
    "unresolved": [{"path": "/elsewhere/ns/s.sock", "class": sockets.REPORTED}],
    "unchecked": [],
}
GOOD = {
    "host_masks": {"/run": {"type": "tmpfs", "readonly": True, "extra": []}},
    "var_run": "/run",
    "inventory": INVENTORY,
    "inside": {"reachable": [{"path": "/var/lib/sss/pipes/nss", "inside": ["/var/lib/sss/pipes/nss"]}], "errors": [],
               "seconds": 0.002},
    "display_files": {"/home/u/.Xauthority": "empty"},
    "env_set": [],
    "terminal": {"tty_nr": 0, "dev_tty": "ENXIO", "session_leader": False},
}


@pytest.fixture(autouse=True)
def no_host_facts(monkeypatch):
    monkeypatch.setattr(probe, "host_masks", lambda: ("/run",))  # whatever host runs this


def test_a_good_sandbox_passes_rows_2_to_4_with_their_facts():
    row = probe._row2(LAYOUT, GOOD)
    assert row["ok"] is True, row["reason"]
    assert row["sockets"] == [{"path": "/var/lib/sss/pipes/nss", "class": sockets.REPORTED,
                               "inside": ["/var/lib/sss/pipes/nss"]}]
    assert (row["table"], row["checked"]) == (40, 2)
    assert probe._row3(GOOD)["ok"] is True
    assert probe._row4(GOOD) == {"name": "terminal", "ok": True, "reason": None, **GOOD["terminal"]}


def test_row_2_names_every_residual_of_the_inventory_on_the_label():
    """D-CS2-3: what the table cannot show is named on the label, each of the four: another network namespace and a
    move or link into another directory (always), another mount namespace (the paths that do not resolve) and a
    relative bind (counted)."""
    row = probe._row2(LAYOUT, GOOD)
    assert row["not_covered"] == ["a socket bound in another network namespace",
                                  "a socket moved or linked into another directory"]
    assert row["unresolved"] == INVENTORY["unresolved"] and row["relative"] == INVENTORY["relative"]


def test_an_abstract_socket_of_a_failing_class_is_a_fact_of_the_shared_network_and_does_not_fail_the_row():
    """D-CS2-5: until CS-3 gives runs their own network namespace, an abstract socket is listed with its class under
    the shared network, and `required` claims nothing about it."""
    row = probe._row2(LAYOUT, GOOD)
    assert row["ok"] is True
    assert row["abstract"] == {"network": "shared", "sockets": [{"name": "@/tmp/.X11-unix/X0", "class": "display"}]}


@pytest.mark.parametrize(("change", "says"), [
    ({"inventory": {"error": "the socket table could not be read (FileNotFoundError: x)", "seconds": 0.0}},
     "could not be read"),
    ({"inventory": {**INVENTORY, "control": False}}, "does not list the probe's own listener"),
    ({"inside": {**GOOD["inside"], "errors": [{"path": "/home/u/x/s", "error": "EACCES"}]}}, "could not check"),
    ({"inside": {**GOOD["inside"], "reachable": [{"path": "/home/u/.cache/cm/master",
                                                   "inside": ["/home/u/.cache/cm/master", "/media/p/master"]}]}},
     "credential socket is reachable: /home/u/.cache/cm/master (inside at"),
])
def test_row_2_fails_closed_on_its_inventory(change, says):
    """D-CS2-2: a table that cannot be read, one that does not list the probe's own listener (not this namespace's), a
    check inside that errors, and a reachable socket of a failing class each fail the row."""
    row = probe._row2(LAYOUT, {**GOOD, **change})
    assert row["ok"] is False and says in row["reason"]


@pytest.mark.parametrize(("change", "says"), [
    ({"host_masks": {"/run": {"type": "ext4", "readonly": True, "extra": []}}}, "not a read-only tmpfs"),
    ({"host_masks": {"/run": {"type": "tmpfs", "readonly": False, "extra": []}}}, "not a read-only tmpfs"),
    ({"host_masks": {"/run": {"type": "tmpfs", "readonly": True, "extra": ["/run/dbus"]}}}, "did not put there"),
    ({"host_masks": {}}, "not a read-only tmpfs"),  # nothing reported: fails closed
    ({"var_run": "/srv/run"}, "outside the masked"),
])
def test_row_2_fails_closed_on_its_masks(change, says):
    row = probe._row2(LAYOUT, {**GOOD, **change})
    assert row["ok"] is False and says in row["reason"]


def test_row_2_checks_the_hosts_run_even_when_the_layout_lost_its_mask():
    """The row asks the host which trees are masked whole, not only the layout: a layout without its /run mask fails."""
    lost = L.Layout(role="reviewer", access="read", bwrap="/usr/bin/bwrap", writable=(), readonly=(), hide_host=())
    row = probe._row2(lost, {**GOOD, "host_masks": {"/run": {"type": "tmpfs", "readonly": False, "extra": ["/x"]}}})
    assert row["ok"] is False
    assert "/run is not a read-only tmpfs inside" in row["reason"] and "/run holds what" in row["reason"]


def test_an_unreadable_table_is_an_error_the_row_fails_on(monkeypatch):
    def unreadable(**_kw):
        raise FileNotFoundError(2, "No such file or directory", "/proc/net/unix")

    monkeypatch.setattr(sockets, "inventory", unreadable)
    got = probe._inventory(own=(), env={})
    assert got["error"].startswith("the socket table could not be read")
    assert probe._row2(LAYOUT, {**GOOD, "inventory": got})["ok"] is False


# ----------------------------------------------------------------------------------------- the probe's matching
def payload() -> dict:
    """The probe's definitions, without running it (its main part runs only as ``__main__``)."""
    namespace: dict = {"__name__": "aew_probe_payload"}
    exec(probe._PAYLOAD, namespace)  # noqa: S102 (the module's own constant, read for its functions)
    return namespace


MOUNTS = [("8:1", "/", "/", "xfs", True), ("8:2", "/", "/home", "xfs", True),
          ("8:2", "/u/proj", "/run/media/p", "xfs", True), ("0:50", "/", "/run", "tmpfs", True)]


def test_the_probe_looks_for_a_socket_at_every_mount_of_its_filesystem_that_holds_it():
    """D-CS2-2: the same file may be at more than one path inside (a bind of it, or of a parent)."""
    inside_paths = payload()["inside_paths"]
    socket = {"path": "/home/u/proj/s", "majmin": "8:2", "fspath": "/u/proj/s"}
    assert inside_paths(socket, MOUNTS) == ["/home/u/proj/s", "/run/media/p/s"]
    assert inside_paths({**socket, "fspath": None}, MOUNTS) == ["/home/u/proj/s"]  # no mount of it known: its own path
    assert inside_paths({**socket, "majmin": "8:9"}, MOUNTS) == ["/home/u/proj/s"]  # another filesystem's mounts


def test_the_probe_counts_a_socket_reachable_only_when_the_same_file_is_there():
    """Reachable means the same socket file, by device and inode, at a path inside: a same-named socket of the
    sandbox's own, or a mask in its place, does not count; a check that errors is reported, not passed."""
    ns = payload()
    files = {"/home/u/proj/s": (2050, 9), "/run/media/p/s": (2050, 9), "/home/u/other/s": (2050, 77)}
    errors = {"/home/u/locked/s": errno.EACCES}

    def lstat(path):
        if path in errors:
            raise PermissionError(errors[path], "denied", path)
        if path not in files:
            raise FileNotFoundError(2, "absent", path)
        return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o755, st_dev=files[path][0], st_ino=files[path][1])

    ns["os"] = SimpleNamespace(lstat=lstat)
    found, failed = ns["reachable"]([
        {"path": "/home/u/proj/s", "dev": 2050, "ino": 9, "majmin": "8:2", "fspath": "/u/proj/s"},
        {"path": "/home/u/other/s", "dev": 2050, "ino": 10, "majmin": "8:2", "fspath": None},   # another file there
        {"path": "/run/user/1000/bus", "dev": 26, "ino": 5, "majmin": "0:26", "fspath": "/bus"},  # under a mask
        {"path": "/home/u/locked/s", "dev": 2050, "ino": 11, "majmin": "8:2", "fspath": None},
    ], MOUNTS)
    assert found == [{"path": "/home/u/proj/s", "inside": ["/home/u/proj/s", "/run/media/p/s"]}]
    assert failed == [{"path": "/home/u/locked/s", "error": "EACCES"}]


# --------------------------------------------------------------------------------------------- aew doctor
@pytest.mark.parametrize(("abstract", "status"), [
    ([{"name": "@/tmp/.X11-unix/X0", "class": "display"}, {"name": "@/tmp/dbus-1", "class": "credential"},
      {"name": "@/tmp/.ICE-unix/1", "class": "reported"}], "WARN"),
    ([{"name": "@ISCSIADM_ABSTRACT_NAMESPACE", "class": "reported"}], "PASS"),
])
def test_doctor_warns_of_each_failing_class_of_abstract_socket_on_the_shared_network(monkeypatch, abstract, status):
    """D-CS2-5: a passing sandbox with an abstract socket of a failing class is a WARN naming its class and that
    CS-3's network namespace closes it; a reported one is not."""
    monkeypatch.setattr(C, "supported", lambda: True)
    monkeypatch.setattr(C, "for_run", lambda **_kw: LAYOUT)
    monkeypatch.setattr(probe, "self_test", lambda *_a, **_kw: {"ok": True, "reason": None, "rows": {
        "2": {"abstract": {"network": "shared", "sockets": abstract}}}})
    monkeypatch.setattr(probe, "mechanism", lambda _layout: "bubblewrap 0.4.0")
    got, detail = C.doctor(None, "unsupported")
    assert got == status
    if status == "WARN":
        assert detail.endswith("; abstract credential socket on the shared network; CS-3's network namespace closes "
                               "it; abstract display socket on the shared network; CS-3's network namespace closes it")


@pytest.mark.parametrize(("change", "says"), [
    ({"terminal": {"tty_nr": 34816, "dev_tty": "opened", "session_leader": True}}, "controlling terminal"),
    ({"terminal": {"tty_nr": 0, "dev_tty": "opened", "session_leader": False}}, "controlling terminal"),
    ({"terminal": {"tty_nr": 34816, "dev_tty": "ENXIO", "session_leader": False}}, "controlling terminal"),
    ({"terminal": {}}, "controlling terminal"),  # nothing reported: fails closed
])
def test_row_4_fails_closed_on_a_controlling_terminal(change, says):
    row = probe._row4({**GOOD, **change})
    assert row["ok"] is False and says in row["reason"]


def test_row_4_records_whether_the_process_leads_its_session_and_does_not_require_it():
    """Under --new-session bubblewrap's own process in the sandbox leads the session (seen on CI): what the kernel's
    TIOCSTI check reads is the controlling terminal, which the process has none of."""
    row = probe._row4({**GOOD, "terminal": {"tty_nr": 0, "dev_tty": "ENXIO", "session_leader": False}})
    assert row["ok"] is True and row["session_leader"] is False


@pytest.mark.parametrize(("change", "says"), [
    ({"display_files": {"/home/u/.Xauthority": "readable"}}, "is readable"),
    ({"env_set": ["DISPLAY"]}, "DISPLAY reaches"),
])
def test_row_3_fails_closed(change, says):
    row = probe._row3({**GOOD, **change})
    assert row["ok"] is False and says in row["reason"]
