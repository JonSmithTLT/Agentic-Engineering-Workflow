"""The launch self-test's judgement (STG-05 CB-12, rows 2 to 5), on synthetic probe output.

Pure: nothing starts bubblewrap, so it runs on every platform. The rows on a real sandbox, and each failing closed when
a protection is taken out, are in tests/integration/test_containment.py. Row 4 is judged here, and on a real sandbox
by the pseudo-terminal launcher test there. Row 2's socket inventory (the designer's D-CS2-2 to D-CS2-5) is judged
here on synthetic host inventories and synthetic probe output, and the probe's own matching on synthetic mount tables.
"""

from __future__ import annotations

import contextlib
import errno
import os
import stat
import sys
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
    """D-CS2-3 and the review of #244: every limit of the inventory is named on the label, always, and the instances
    the table shows are listed: paths that do not resolve here (another mount namespace), relative binds (counted),
    and sockets checked at their own paths only, as no mount of their filesystem is known above any spelling."""
    row = probe._row2(LAYOUT, GOOD)
    assert row["not_covered"] == [
        "a socket bound in another network namespace",
        "a socket moved or linked into another directory",
        "a socket bound in another mount namespace at a path that names a different socket here",
        "a socket bound after the launch's check: the inventory is as of the launch",
        "a socket bound through a file descriptor's path (/proc/self/fd/<n>/...): unresolved or unchecked here",
        "a socket whose path the launcher could not check: recorded under unchecked, not failed"]
    assert row["unresolved"] == INVENTORY["unresolved"] and row["relative"] == INVENTORY["relative"]
    assert row["untranslated"] == []
    nss = {**INVENTORY["candidates"][0], "fspath": None}
    alone = [{"path": nss["path"], "class": sockets.REPORTED}]
    for real, untranslated in ((None, alone), ({"path": "/srv/nss", "fspath": None}, alone),
                               ({"path": "/srv/nss", "fspath": "/srv/nss"}, [])):
        inventory = {**INVENTORY, "candidates": [{**nss, "real": real}, INVENTORY["candidates"][1]]}
        assert probe._row2(LAYOUT, {**GOOD, "inventory": inventory})["untranslated"] == untranslated


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


def test_the_probes_control_listener_is_made_under_tmp_whatever_tmpdir_says(monkeypatch, tmp_path):
    """Review of #244, n4: the control listener's directory is made in the host's /tmp, which no sandbox sees (each
    has its own), even when the launching TMPDIR names a tree the read-only root shows. Synthetic: nothing is bound."""
    made: dict = {}

    def mkdtemp(**kw):
        made.update(kw)
        (tmp_path / "aew-probe-x").mkdir()
        return str(tmp_path / "aew-probe-x")

    class Listener:
        def __init__(self, *_a):
            pass

        def bind(self, path):
            made["bound"] = path

        def listen(self, _n):
            pass

        def close(self):
            pass

    isdir = probe.os.path.isdir
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr(probe.tempfile, "tempdir", None)
    monkeypatch.setattr(probe, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(probe, "socket", SimpleNamespace(socket=Listener, AF_UNIX=1, SOCK_STREAM=1))
    monkeypatch.setattr(probe.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(probe.os.path, "isdir", lambda p: p == "/tmp" or isdir(p))
    with probe._control() as (path, directory):
        assert (made["dir"], made["prefix"]) == ("/tmp", "aew-probe-")
        assert made["bound"] == path == os.path.join(directory, "control")


def test_a_table_that_does_not_parse_is_an_error_the_row_fails_on_never_a_crash(monkeypatch):
    """Review of #244: a record of the kernel's tables that does not parse (sockets.table, sockets.mounts) refuses the
    launch with a reason on the label; it is neither dropped nor an exception out of the self-test."""
    def unparsed(**_kw):
        raise ValueError("line 9 of /proc/net/unix is not a socket's record: b'x'")

    monkeypatch.setattr(sockets, "inventory", unparsed)
    monkeypatch.setattr(probe, "_control", lambda: contextlib.nullcontext(("/tmp/c/control", "/tmp/c")))
    got = probe._inventory(own=(), env={})
    assert got["error"] == ("the socket inventory could not parse the kernel's tables (line 9 of /proc/net/unix is "
                            "not a socket's record: b'x')")
    row = probe._row2(LAYOUT, {**GOOD, "inventory": got})
    assert row["ok"] is False and "could not parse" in row["reason"]


UNKNOWN_HOLDER = {"path": "/home/u/tools/svc.sock", "listed": "/home/u/tools/svc.sock", "class": sockets.CREDENTIAL,
                  "holder": sockets.UNIDENTIFIED, "dev": 2050, "ino": 50, "majmin": "8:2",
                  "fspath": "/u/tools/svc.sock"}
REACHED = {**GOOD, "inventory": {**INVENTORY, "candidates": [*INVENTORY["candidates"], UNKNOWN_HOLDER],
                                 "unreadable": [{"pid": 11, "name": "svc"}]},
           "inside": {**GOOD["inside"], "reachable": [{"path": UNKNOWN_HOLDER["path"],
                                                        "inside": [UNKNOWN_HOLDER["path"]]}]}}


def test_a_reachable_socket_whose_holder_cannot_be_identified_fails_row_2_naming_the_remedy():
    """The designer's D-CS2-6: a reachable listening socket of the launching user's whose holder the launcher cannot
    identify is a credential; the row fails, naming the socket and the remedy, and records the unreadable process."""
    row = probe._row2(LAYOUT, REACHED)
    assert row["ok"] is False
    assert row["reason"] == ("a credential socket is reachable: /home/u/tools/svc.sock" + probe.UNIDENTIFIED_REMEDY)
    assert row["sockets"] == [{"path": UNKNOWN_HOLDER["path"], "class": sockets.CREDENTIAL,
                               "inside": [UNKNOWN_HOLDER["path"]], "holder": sockets.UNIDENTIFIED}]
    assert row["unreadable_processes"] == [{"pid": 11, "name": "svc"}]


def test_doctor_names_a_socket_whose_holder_cannot_be_identified_and_the_remedy(monkeypatch):
    monkeypatch.setattr(C, "supported", lambda: True)
    monkeypatch.setattr(C, "for_run", lambda **_kw: LAYOUT)
    row = probe._row2(LAYOUT, REACHED)
    monkeypatch.setattr(probe, "self_test", lambda *_a, **_kw: {"ok": False, "reason": f"row 2 (run_and_sockets): "
                                                                f"{row['reason']}", "rows": {"2": row}})
    status, detail = C.doctor({"containment": {"mode": "required"}}, "unsupported")
    assert status == "FAIL" and "/home/u/tools/svc.sock" in detail
    assert "stop that process, move its socket under a masked path, or set containment.mode: allow_weaker" in detail


def test_row_2_records_what_the_host_could_not_check():
    """A socket path the launcher could not check (an error other than its absence) is on the label, with its class
    and why, and so is each of the launching user's processes it could not read (review of #244)."""
    unchecked = [{"path": "/home/other/private/s.sock", "class": sockets.REPORTED, "error": "Permission denied"}]
    row = probe._row2(LAYOUT, {**GOOD, "inventory": {**INVENTORY, "unchecked": unchecked}})
    assert row["unchecked"] == unchecked
    unreadable = [{"pid": 11, "name": "svc"}]  # the launching user's, not readable in /proc
    row = probe._row2(LAYOUT, {**GOOD, "inventory": {**INVENTORY, "unreadable": unreadable}})
    assert row["unreadable_processes"] == unreadable and row["ok"] is True


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


def test_the_probe_checks_a_socket_at_its_resolved_spelling_too():
    """Review of #244: a socket is also looked for at the path its directory resolves to on the host, and at that
    spelling's place under every mount of its filesystem."""
    ns = payload()
    linked = {"path": "/srv/link/s", "dev": 2050, "ino": 9, "majmin": "8:2", "fspath": None,
              "real": {"path": "/home/u/proj/s", "fspath": "/u/proj/s"}}
    assert ns["inside_paths"](linked, MOUNTS) == ["/srv/link/s", "/home/u/proj/s", "/run/media/p/s"]

    def lstat(path):
        if path != "/home/u/proj/s":
            raise FileNotFoundError(2, "absent", path)
        return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o755, st_dev=2050, st_ino=9)

    ns["os"] = SimpleNamespace(lstat=lstat)
    assert ns["reachable"]([linked], MOUNTS) == ([{"path": "/srv/link/s", "inside": ["/home/u/proj/s"]}], [])
    assert ns["reachable"]([{**linked, "real": None}], MOUNTS) == ([], [])


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


@pytest.mark.parametrize("byte", [b"\r", b"\x0b", b"\x0c"])
def test_the_probe_reads_its_mount_table_as_the_kernel_writes_it(tmp_path, byte):
    """Review of #244: inside, as on the host (sockets.mounts), fields are split at single spaces only and unescaped,
    and a line that does not parse raises, which the row fails on (`inside.errors`)."""
    mountinfo = payload()["mountinfo"]
    path = tmp_path / "mountinfo"
    path.write_bytes(b"22 1 8:1 / / ro,relatime shared:1 - xfs /dev/sda1 rw\n"
                     b"23 22 8:2 /u/p\\040q /media/p" + byte + b"t rw - xfs /dev/sda2 rw\n"
                     b"24 22 0:50 / /run ro,nosuid - tmpfs tmpfs ro\n")
    assert mountinfo(str(path)) == [("8:1", "/", "/", "xfs", True),
                                    ("8:2", "/u/p q", "/media/p" + byte.decode() + "t", "xfs", False),
                                    ("0:50", "/", "/run", "tmpfs", True)]
    path.write_bytes(b"22 1 8:1 / / ro - xfs /dev/sda1 rw\n23 22 8:2 /u/p /media/p\n")
    with pytest.raises(ValueError, match="is not a mount's"):
        mountinfo(str(path))


def test_a_mount_table_the_probe_cannot_read_or_parse_is_an_error_row_2_fails_on(tmp_path):
    mount_table = payload()["mount_table"]
    path = tmp_path / "mountinfo"
    path.write_bytes(b"22 1 8:1 / / ro - xfs /dev/sda1 rw\n")
    assert mount_table(str(path)) == ([("8:1", "/", "/", "xfs", True)], [])
    path.write_bytes(b"22 1 8:1 / / ro xfs /dev/sda1 rw\n")
    table, errors = mount_table(str(path))
    assert table == [] and [e["path"] for e in errors] == [str(path)] and "is not a mount's" in errors[0]["error"]
    assert mount_table(str(tmp_path / "absent"))[1][0]["path"] == str(tmp_path / "absent")
    row = probe._row2(LAYOUT, {**GOOD, "inside": {**GOOD["inside"], "errors": errors}})
    assert row["ok"] is False and f"could not check {path} inside" in row["reason"]


def test_the_probe_is_handed_each_spelling_of_each_socket():
    linked = {**INVENTORY["candidates"][1], "real": {"path": "/srv/cm/master", "fspath": "/srv/cm/master"}}
    assert probe._candidates({**INVENTORY, "candidates": [INVENTORY["candidates"][0], linked]}) == [
        {"path": "/var/lib/sss/pipes/nss", "dev": 2050, "ino": 7, "majmin": "8:2", "fspath": "/var/lib/sss/pipes/nss",
         "real": None},
        {"path": "/home/u/.cache/cm/master", "dev": 2050, "ino": 8, "majmin": "8:2", "fspath": "/u/.cache/cm/master",
         "real": {"path": "/srv/cm/master", "fspath": "/srv/cm/master"}}]


@pytest.mark.skipif(sys.platform == "win32", reason="the probe runs in a Linux sandbox: its paths are POSIX, and a "
                                                    "symlink needs a privilege on Windows")
def test_the_probe_finds_in_a_masked_tree_exactly_what_the_layout_did_not_put_there(tmp_path):
    """Review of #244, m2: row 2's "holding only what the layout put there" rests on the probe's listing of each mask.
    In a synthetic tree, the paths the layout put there and the directories on the way to them are not listed, nor is
    anything under them; any other entry is, a link included, and a link on the way to an allowed path too (review of
    #244, n3)."""
    masked_tree = payload()["masked_tree"]
    root = tmp_path / "run"
    allowed = root / "media" / "u" / "d" / "proj"
    (allowed / "inside").mkdir(parents=True)
    (root / "media" / "u" / "other").write_text("x")
    (root / "media" / "u" / "d" / ".hidden").mkdir()
    (root / "lnk").symlink_to(root / "media")
    (tmp_path / "elsewhere" / "proj").mkdir(parents=True)
    (root / "via").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    beyond = root / "via" / "proj"  # allowed, but reached through a link
    assert sorted(masked_tree(str(root), {str(allowed), str(beyond)})) == sorted(
        str(p) for p in (root / "media" / "u" / "other", root / "media" / "u" / "d" / ".hidden", root / "lnk",
                         root / "via"))
    assert masked_tree(str(root), {str(allowed), str(beyond), str(root / "via"), str(root / "media" / "u" / "other"),
                                   str(root / "media" / "u" / "d" / ".hidden"), str(root / "lnk")}) == []


# --------------------------------------------------------------------------------------------- aew doctor
@pytest.mark.parametrize(("abstract", "status"), [
    ([{"name": "@/tmp/.X11-unix/X0", "class": "display"}, {"name": "@/tmp/dbus-1", "class": "credential"},
      {"name": "@/tmp/.ICE-unix/1", "class": "reported"}], "WARN"),
    ([{"name": "@ISCSIADM_ABSTRACT_NAMESPACE", "class": "reported"}], "PASS"),
])
def test_doctor_warns_of_each_failing_class_of_abstract_socket_on_the_shared_network(monkeypatch, abstract, status):
    """D-CS2-5: on the host's network (containment.network.mode: shared), a passing sandbox with an abstract socket of
    a failing class is a WARN naming its class and that the default network mode closes it; a reported one is not."""
    monkeypatch.setattr(C, "supported", lambda: True)
    monkeypatch.setattr(C, "for_run", lambda **_kw: LAYOUT)
    monkeypatch.setattr(probe, "self_test", lambda *_a, **_kw: {"ok": True, "reason": None, "rows": {
        "2": {"abstract": {"network": "shared", "sockets": abstract}}}})
    monkeypatch.setattr(probe, "mechanism", lambda _layout: "bubblewrap 0.4.0")
    got, detail = C.doctor({"containment": {"network": {"mode": "shared"}}}, "unsupported")
    assert got == status
    if status == "WARN":
        assert detail.endswith("; abstract credential socket on the shared network; the default network mode "
                               "(proxy_only) closes it; abstract display socket on the shared network; the default "
                               "network mode (proxy_only) closes it")


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
