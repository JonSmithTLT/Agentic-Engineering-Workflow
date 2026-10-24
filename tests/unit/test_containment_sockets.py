"""The socket inventory (STG-05 CB-03; the designer's D-CS2-2 and D-CS2-3): what fails a launch, what is the run's own,
what is only reported, and how the kernel's socket table becomes the paths a sandbox is checked for.

Pure: every input is synthetic (names, table text, stat results, mount tables), nothing binds a socket, so it runs on
every platform. The real self-test on a real host is in tests/integration/test_containment.py.
"""

from __future__ import annotations

import os
import stat
import sys
from types import SimpleNamespace

import pytest

from aew.harness.containment import sockets as S

REALDIR = S._realdir  # the host's own resolution, before any test fakes it

# One planted path per row of the table, and the class it must get (the hand-off's list and the Lead's rulings).
PLANTED = {
    S.DISPLAY: ["/tmp/.X11-unix/X0", "/run/user/1000/wayland-0"],
    S.APPROVAL: ["/run/aew-g3/approve.sock", "/run/aew-g3/store/deep/s.sock"],
    S.AEW_SERVICE: ["/run/aew-wis/issuer.sock", "/run/aew-owner/store/owner.sock", "/tmp/aew-bridge-x/s"],
    S.CREDENTIAL: ["/tmp/ssh-XXXX/agent.1234", "/home/u/.gnupg/S.gpg-agent", "/run/user/1000/gnupg/S.gpg-agent.ssh",
                   "/run/user/1000/gnupg/S.scdaemon", "/home/u/.gnupg/S.keyboxd",
                   "/home/u/.cache/git/credential/socket", "/home/u/.git-credential-cache/socket",
                   "/run/user/1000/keyring/control", "/run/user/1000/bus", "/home/u/.1password/agent.sock",
                   "/home/u/.bitwarden-ssh-agent.sock", "/home/u/.cache/vault-agent.socket", "/run/user/1000/gcr/ssh",
                   "/srv/keys/agent.sock"],
    S.ESCAPE: ["/run/dbus/system_bus_socket", "/tmp/tmux-1000/default", "/run/screen/S-u/123.pts-0.host",
               "/tmp/emacs1000/server", "/run/user/1000/vscode-ipc-0a1b.sock", "/var/run/docker.sock",
               "/run/user/1000/podman/podman.sock", "/run/containerd/containerd.sock",
               "/run/user/1000/systemd/private"],
}
ORDINARY = ["/var/lib/sss/pipes/nss", "/var/lib/sss/pipes/pam", "/home/u/project/app.sock", "/srv/x11/note.sock",
            "/home/u/.aew-test-tmp/contain-1/s.sock", "/home/u/AEW-web/dev.sock",
            "/home/u/aew-review/runs/b-A-1/sock/api.sock", "/srv/aew-x/s.sock"]


@pytest.mark.parametrize("cls", sorted(PLANTED))
def test_each_failing_class_matches_its_planted_paths_and_nothing_else(cls):
    assert cls in S.FAILING
    got = {p: S.classify(p, env={}) for p in PLANTED[cls]}
    assert got == dict.fromkeys(PLANTED[cls], cls)
    assert all(S.classify(p, env={}) != cls for other, paths in PLANTED.items() if other != cls for p in paths)


def test_an_unlisted_socket_is_reported_not_refused():
    """A site's ordinary services never block a run (SSSD's pipes): reported, not failing. A directory named like
    AEW's own is AEW's only directly in a runtime root: not upper-case `AEW-<topic>` (the operator's checkouts), and
    not an `aew-*` directory anywhere else (a reviewer's tree on the Rocky VM held stale sockets of an old study)."""
    assert {p: S.classify(p, env={}) for p in ORDINARY} == dict.fromkeys(ORDINARY, S.REPORTED)
    assert S.REPORTED not in S.FAILING and S.OWN not in S.FAILING


def test_host_derived_paths_are_classified_from_the_launching_environment():
    """Whatever their paths, the sockets the launching environment names are the display's, the ssh agent's and the
    session bus's (CB-04's variables): a custom location is still found."""
    env = {"DISPLAY": ":7.0", "WAYLAND_DISPLAY": "custom-wl", "XDG_RUNTIME_DIR": "/srv/rt",
           "SSH_AUTH_SOCK": "/srv/keys/my-agent", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/srv/rt/sbus,guid=abc;"
                                                                              "unix:abstract=/tmp/x"}
    assert S.classify("/tmp/.X11-unix/X7", env=env) == S.DISPLAY
    assert S.classify("/srv/rt/custom-wl", env=env) == S.DISPLAY
    assert S.classify("/srv/keys/my-agent", env=env) == S.CREDENTIAL
    assert S.classify("/srv/rt/sbus", env=env) == S.CREDENTIAL
    assert S.classify("/srv/keys/my-agent", env={}) == S.REPORTED  # without the variable, nothing marks it
    assert S.classify("/tmp/.X11-unix/X7", env={"DISPLAY": "remote.example:7"}) == S.DISPLAY  # by its own name too


def test_an_aew_runtime_directory_counts_in_the_launching_environments_runtime_root_too():
    env = {"XDG_RUNTIME_DIR": "/srv/rt"}
    assert S.classify("/srv/rt/aew-g3/s", env=env) == S.APPROVAL
    assert S.classify("/srv/rt/aew-wis/s", env=env) == S.AEW_SERVICE
    assert S.classify("/srv/rt/aew-wis/s", env={}) == S.REPORTED
    assert S.classify("/run/aew-g3", env={}) == S.REPORTED  # a socket named so, not in a directory of AEW's


def test_the_runs_own_bridge_socket_is_its_own_never_a_failure():
    own = ("/tmp/aew-bridge-abc",)
    assert S.classify("/tmp/aew-bridge-abc/s", own=own, env={}) == S.OWN
    assert S.classify("/tmp/aew-bridge-other/s", own=own, env={}) == S.AEW_SERVICE  # another run's bridge


# ------------------------------------------------------------------------------------------- the kernel's table
TABLE_TEXT = (
    "Num       RefCount Protocol Flags    Type St Inode Path\n"
    "0000000000000000: 00000002 00000000 00010000 0001 01 101 /home/u/.cache/svc/listen.sock\n"
    "0000000000000000: 00000003 00000000 00000000 0001 03 102 /home/u/.cache/svc/listen.sock\n"
    "0000000000000000: 00000002 00000000 00010000 0001 01 103 @/tmp/.X11-unix/X0\n"
    "0000000000000000: 00000002 00000000 00010000 0001 01 104 relative.sock\n"
    "0000000000000000: 00000002 00000000 00000000 0002 01 105\n"
    "0000000000000000: 00000002 00000000 00010000 0001 01 106 /srv/with space/s.sock\n"
)


def test_the_table_is_parsed_into_named_sockets_listening_or_not(tmp_path):
    """Every named socket of the table: by path, abstract (@) or relative as bound; an unnamed one is no door by name.
    A connection accepted on a listener is listed under the listener's name (102)."""
    path = tmp_path / "unix"
    path.write_bytes(TABLE_TEXT.encode())
    entries = S.table(str(path))
    assert [(e.inode, e.name, e.listening) for e in entries] == [
        (101, "/home/u/.cache/svc/listen.sock", True), (102, "/home/u/.cache/svc/listen.sock", False),
        (103, "@/tmp/.X11-unix/X0", True), (104, "relative.sock", True), (106, "/srv/with space/s.sock", True)]


def test_an_unreadable_table_raises_for_the_caller_to_fail_closed(tmp_path):
    with pytest.raises(OSError):
        S.table(str(tmp_path / "absent"))


RECORD = b"0000000000000000: 00000002 00000000 00010000 0001 01 %d %s\n"


@pytest.mark.parametrize("byte", [b"\r", b"\x0b", b"\x0c", b"\t", b"\x85"])
def test_a_name_is_listed_whole_whatever_bytes_it_holds(tmp_path, byte):
    """Review of #244: the table is read as bytes and split at the newline only."""
    name = b"/home/u/d" + byte + b"x/s.sock"
    path = tmp_path / "unix"
    path.write_bytes(TABLE_TEXT.encode() + RECORD % (107, name))
    assert S.table(str(path))[-1] == S.Entry(107, name.decode("utf-8", "surrogateescape"), True)


@pytest.mark.parametrize("tail", [
    b"/home/u/d\nx/s.sock\n",
    b"/home/u/d\n0000000000000000: 00000002 00000000 00010000 0001 01 x9 /a b c\n",
    b"/home/u/s.sock\n\n",
], ids=["short", "malformed", "empty"])
def test_a_record_that_does_not_parse_raises_for_the_row_to_fail_closed(tmp_path, tail):
    """A line that matches no record of the kernel's format makes the table raise ValueError; it is never dropped (the
    row then fails closed, tests/unit/test_containment_probe.py)."""
    path = tmp_path / "unix"
    path.write_bytes(TABLE_TEXT.encode() + b"0000000000000000: 00000002 00000000 00010000 0001 01 107 " + tail)
    with pytest.raises(ValueError, match="is not a socket's record"):
        S.table(str(path))


def test_a_table_without_its_header_or_its_last_newline_raises(tmp_path):
    path = tmp_path / "unix"
    path.write_bytes(TABLE_TEXT.encode().split(b"\n", 1)[1])
    with pytest.raises(ValueError, match="no header"):
        S.table(str(path))
    path.write_bytes(TABLE_TEXT.encode().rstrip(b"\n"))
    with pytest.raises(ValueError, match="does not end with a newline"):
        S.table(str(path))


MOUNTINFO = (b"22 1 8:1 / / ro,relatime shared:1 - xfs /dev/sda1 rw\n"
             b"23 22 8:2 /u/p\\040q /media/a\\134b\\011c ro - xfs /dev/sda2 rw\n")


@pytest.mark.parametrize("byte", [b"\r", b"\x0b", b"\x0c"])
def test_the_mount_table_is_split_at_single_spaces_and_unescaped(tmp_path, byte):
    """Review of #244: mountinfo escapes a space, a tab, a newline and a backslash in a path as octal and writes every
    other byte raw, so its fields are split at single spaces only."""
    path = tmp_path / "mountinfo"
    path.write_bytes(MOUNTINFO + b"24 22 8:3 /x /mnt/p" + byte + b"t rw - ext4 /dev/sda3 rw\n")
    assert S.mounts(str(path)) == [("8:1", "/", "/"), ("8:2", "/u/p q", "/media/a\\b\tc"),
                                   ("8:3", "/x", "/mnt/p" + byte.decode() + "t")]


@pytest.mark.parametrize("line", [b"24 22 8:3 /x /mnt/p rw ext4 /dev/sda3 rw\n", b"24 22 x /x /mnt rw - ext4 s rw\n",
                                  b"24 22 8:3 /x\n", b"\n"], ids=["no-separator", "majmin", "short", "empty"])
def test_a_mount_line_that_does_not_parse_raises(tmp_path, line):
    path = tmp_path / "mountinfo"
    path.write_bytes(MOUNTINFO + line)
    with pytest.raises(ValueError, match="is not a mount's"):
        S.mounts(str(path))


@pytest.mark.parametrize(("name", "cls"), [
    ("@/tmp/.X11-unix/X0", S.DISPLAY), ("@/tmp/dbus-HSC1vEMv", S.CREDENTIAL), ("@/containerd-shim/abc.sock", S.ESCAPE),
    ("@/tmp/.ICE-unix/3020", S.REPORTED), ("@ISCSIADM_ABSTRACT_NAMESPACE", S.REPORTED),
])
def test_an_abstract_socket_is_classified_by_the_same_table_without_its_at_sign(name, cls):
    """D-CS2-2's abstract names: X11's display, a session bus, a container engine's shim; ICE and root's iscsi sockets
    are reported (the designer's addendum)."""
    assert S.classify(name, env={}) == cls


def test_the_launching_environments_abstract_display_and_bus_are_failing_wherever_they_are():
    env = {"DISPLAY": ":7", "DBUS_SESSION_BUS_ADDRESS": "unix:abstract=/srv/bus-xyz,guid=1"}
    assert S.classify("@/tmp/.X11-unix/X7", env=env) == S.DISPLAY
    assert S.classify("@/srv/bus-xyz", env=env) == S.CREDENTIAL
    assert S.classify("@/srv/bus-xyz", env={}) == S.REPORTED


@pytest.mark.parametrize(("exe", "cls"), [
    ("Xwayland", S.DISPLAY), ("Xorg", S.DISPLAY), ("ssh", S.CREDENTIAL), ("ssh-agent", S.CREDENTIAL),
    ("gpg-agent", S.CREDENTIAL), ("dbus-broker-launch", S.CREDENTIAL), ("tmux: server", S.ESCAPE),
    ("systemd", S.ESCAPE), ("1password", S.CREDENTIAL), ("bitwarden", S.CREDENTIAL), ("keepassxc", S.CREDENTIAL),
    ("python3.11", None), ("sshd", None), (None, None),
])
def test_a_listener_is_classified_by_its_executable(exe, cls):
    assert S.by_executable(exe) == cls


def test_the_worse_class_wins_and_the_runs_own_stays_its_own():
    assert S.worse(S.REPORTED, S.CREDENTIAL) == S.CREDENTIAL
    assert S.worse(S.DISPLAY, S.CREDENTIAL) == S.DISPLAY  # the first failing one
    assert S.worse(S.REPORTED, None) == S.REPORTED
    assert S.worse(S.OWN, S.CREDENTIAL) == S.OWN


SOCK = stat.S_IFSOCK | 0o755
CONTROL = "/tmp/aew-probe-x/control"


def fake_host(monkeypatch, *, entries, listeners=None, stats=None, directories=None, mounts=(), realdirs=None,
              unreadable=None):
    """The inventory's host inputs, all synthetic: the table's entries, the launching user's listeners
    {inode: executable}, lstat results {path: (dev, ino) or an exception}, directory listings {dir: [(path, dev,
    ino)] or an exception}, the host's mount table, directories that resolve elsewhere {dir: resolved}, and the
    launching user's processes that cannot be read."""
    def stat_of(dev: int, ino: int, uid: int = 0) -> SimpleNamespace:  # owned by root unless given
        return SimpleNamespace(st_mode=SOCK, st_dev=dev, st_ino=ino, st_uid=uid)

    def lstat(path):
        found = (stats or {}).get(path, FileNotFoundError(path))
        if isinstance(found, Exception):
            raise found
        return stat_of(*found)

    def socket_files(directory):
        found = (directories or {}).get(directory, FileNotFoundError(directory))
        if isinstance(found, Exception):
            raise found
        return [(p, stat_of(dev, ino)) for p, dev, ino in found]

    monkeypatch.setattr(S, "table", lambda path=S.TABLE: [S.Entry(*e) for e in entries])
    monkeypatch.setattr(S, "listeners", lambda inodes: ({i: x for i, x in (listeners or {}).items() if i in inodes},
                                                        list(unreadable or [])))
    monkeypatch.setattr(S, "mounts", lambda path=S.MOUNTINFO: list(mounts))
    monkeypatch.setattr(S, "_stat", lstat)
    monkeypatch.setattr(S, "_socket_files", socket_files)
    monkeypatch.setattr(S, "_majmin", lambda dev: f"{dev >> 8}:{dev & 0xff}")
    monkeypatch.setattr(S, "_realdir", lambda directory: (realdirs or {}).get(directory, directory))
    monkeypatch.setattr(S, "_uid", lambda: 1000)  # the launching user


def test_the_inventory_lists_each_path_socket_with_its_class_and_records_the_control(monkeypatch):
    fake_host(monkeypatch, entries=[(1, CONTROL, True), (2, "/home/u/svc/s.sock", True),
                                    (3, "/home/u/svc/s.sock", False), (4, "/home/u/cm/hashed", True)],
              listeners={4: "ssh"}, stats={CONTROL: (0x0801, 9), "/home/u/svc/s.sock": (0x0802, 10),
                                           "/home/u/cm/hashed": (0x0802, 11)})
    got = S.inventory(control=CONTROL, own=("/tmp/aew-probe-x",), env={})
    assert got["control"] is True and got["table"] == 4
    classes = {c["path"]: c["class"] for c in got["candidates"]}
    assert classes == {CONTROL: S.OWN, "/home/u/svc/s.sock": S.REPORTED, "/home/u/cm/hashed": S.CREDENTIAL}
    assert S.inventory(control="/tmp/other/control", env={})["control"] is False


def test_a_socket_linked_into_place_in_its_directory_is_found_there_with_the_worse_class(monkeypatch):
    """D-CS2-3: a socket bound under a temporary name and linked to its final name in the same directory (OpenSSH's
    ControlMaster, mux.c's muxserver_listen) is listed under the name that is gone; every socket file in that directory
    is checked, each with the worse of its own class and the listed one's."""
    temp = "/home/u/.cache/cm/master.Xy12"
    fake_host(monkeypatch, entries=[(7, temp, True)], listeners={7: "ssh"},
              directories={"/home/u/.cache/cm": [("/home/u/.cache/cm/master", 0x0802, 20),
                                                 ("/home/u/.cache/cm/S.gpg-agent", 0x0802, 21)]})
    got = {c["path"]: c for c in S.inventory(control=CONTROL, env={})["candidates"]}
    assert got["/home/u/.cache/cm/master"]["class"] == S.CREDENTIAL  # the listed one's, from its executable
    assert got["/home/u/.cache/cm/master"]["listed"] == temp
    assert got["/home/u/.cache/cm/S.gpg-agent"]["class"] == S.CREDENTIAL


def test_what_the_inventory_cannot_check_is_recorded_not_dropped(monkeypatch):
    """D-CS2-3's residuals that the table shows: a path that does not resolve here (bound in another mount namespace)
    and a relative bind are recorded with their classes, and so is a path the launching user cannot reach."""
    fake_host(monkeypatch, entries=[(1, "/elsewhere/ns/s.sock", True), (2, "relative.sock", True),
                                    (3, "/home/other/private/s.sock", True), (4, "@/tmp/.X11-unix/X0", True)],
              stats={"/home/other/private/s.sock": PermissionError(13, "Permission denied")})
    got = S.inventory(control=CONTROL, env={})
    assert got["unresolved"] == [{"path": "/elsewhere/ns/s.sock", "class": S.REPORTED}]
    assert got["relative"] == [{"name": "relative.sock", "class": S.REPORTED}]
    assert got["unchecked"] == [{"path": "/home/other/private/s.sock", "class": S.REPORTED,
                                 "error": "Permission denied"}]
    assert got["abstract"] == [{"name": "@/tmp/.X11-unix/X0", "class": S.DISPLAY}]
    assert got["candidates"] == []


def test_each_socket_carries_its_filesystem_and_its_path_within_it_from_the_deepest_mount(monkeypatch):
    """So the sandbox can find the same file under any mount of the same filesystem (D-CS2-2)."""
    fake_host(monkeypatch, entries=[(1, "/home/u/proj/s.sock", True), (2, "/opt/x/s.sock", True)],
              stats={"/home/u/proj/s.sock": (0x0802, 30), "/opt/x/s.sock": (0x0805, 31)},
              mounts=[("8:1", "/", "/"), ("8:2", "/", "/home"), ("8:2", "/u/proj", "/media/p")])
    got = {c["path"]: c for c in S.inventory(control=CONTROL, env={})["candidates"]}
    assert (got["/home/u/proj/s.sock"]["majmin"], got["/home/u/proj/s.sock"]["fspath"]) == ("8:2", "/u/proj/s.sock")
    assert (got["/opt/x/s.sock"]["majmin"], got["/opt/x/s.sock"]["fspath"]) == ("8:5", None)  # no mount of it above


def test_a_socket_listed_through_a_link_is_checked_at_its_resolved_path_too(monkeypatch):
    """Review of #244: a listed path whose directory resolves elsewhere on the host carries that resolved spelling,
    with its own place in its filesystem, for the probe to check inside as well; the class is the worse of the two
    spellings'. A path that resolves to itself carries none."""
    fake_host(monkeypatch, entries=[(1, "/srv/a/link/s.sock", True), (2, "/home/u/svc/s.sock", True),
                                    (3, "/srv/a/link/m.Xy12", True)],
              stats={"/srv/a/link/s.sock": (0x0802, 40), "/home/u/svc/s.sock": (0x0802, 41)},
              directories={"/srv/a/link": [("/srv/a/link/master", 0x0802, 42)]},
              realdirs={"/srv/a/link": "/home/u/.gnupg"}, mounts=[("8:1", "/", "/"), ("8:2", "/", "/home")])
    got = {c["path"]: c for c in S.inventory(control=CONTROL, env={})["candidates"]}
    assert got["/srv/a/link/s.sock"]["real"] == {"path": "/home/u/.gnupg/s.sock", "fspath": "/u/.gnupg/s.sock"}
    assert got["/srv/a/link/s.sock"]["class"] == S.REPORTED
    assert got["/srv/a/link/master"]["real"] == {"path": "/home/u/.gnupg/master", "fspath": "/u/.gnupg/master"}
    assert got["/home/u/svc/s.sock"]["real"] is None
    fake_host(monkeypatch, entries=[(1, "/srv/a/link/agent.1234", True)],
              stats={"/srv/a/link/agent.1234": (0x0802, 45)}, realdirs={"/srv/a/link": "/tmp/ssh-Xy12"})
    assert S.inventory(control=CONTROL, env={})["candidates"][0]["class"] == S.CREDENTIAL  # the resolved one's


def test_the_launching_users_processes_are_read_for_their_sockets_and_those_it_cannot_read_are_named(monkeypatch):
    """By the launching user's own processes (/proc/<pid>/fd). One whose /proc entries it cannot read is named by pid
    and name for the label, one /proc shows as root's while its real uid is the launching user's included (review of
    #244). Another user's processes, root's own and one that is gone are skipped."""
    procs = {  # pid: (owner shown, real uid, exe, descriptors), or what reading it raises
        "10": (1000, 1000, "/usr/bin/ssh", ["socket:[5]", "pipe:[1]"]),
        "11": (0, 1000, PermissionError(13, "denied"), PermissionError(13, "denied")),
        "12": (0, 0, "/usr/sbin/sshd", ["socket:[6]"]),
        "13": (1001, 1001, "/usr/bin/tmux", ["socket:[7]"]),
        "14": (1000, 1000, FileNotFoundError(2, "gone"), []),
    }

    def field(n):
        def read(pid):
            value = procs[pid][n]
            if isinstance(value, Exception):
                raise value
            return value
        return read

    monkeypatch.setattr(S, "_uid", lambda: 1000)
    monkeypatch.setattr(S, "_pids", lambda: list(procs))
    monkeypatch.setattr(S, "_owner", field(0))
    monkeypatch.setattr(S, "_real_uid", field(1))
    monkeypatch.setattr(S, "_exe", field(2))
    monkeypatch.setattr(S, "_fds", field(3))
    monkeypatch.setattr(S, "_comm", lambda pid: {"11": "svc"}.get(pid))
    assert S.listeners({5, 6, 7}) == ({5: "ssh"}, [{"pid": 11, "name": "svc"}])


def test_a_status_file_is_read_as_bytes_for_its_real_uid(tmp_path):
    path = tmp_path / "status"
    path.write_bytes(b"Name:\tsvc\nUmask:\t0077\nState:\tS (sleeping)\nUid:\t1000\t1000\t1000\t1000\n"
                     b"Gid:\t1000\t1000\t1000\t1000\n")
    assert S._status_uid(str(path)) == 1000
    path.write_bytes(b"Name:\tx\nState:\tS\n")
    assert S._status_uid(str(path)) is None


def test_the_inventory_carries_the_processes_it_could_not_read(monkeypatch):
    fake_host(monkeypatch, entries=[(1, CONTROL, True)], stats={CONTROL: (0x0801, 9)},
              unreadable=[{"pid": 11, "name": "svc"}])
    assert S.inventory(control=CONTROL, env={})["unreadable"] == [{"pid": 11, "name": "svc"}]


@pytest.mark.parametrize(("held", "owner", "listening", "cls"), [
    ({}, 1000, True, S.CREDENTIAL),               # the launching user's, listening, its holder unknown
    ({5: "python3.11"}, 1000, True, S.REPORTED),  # its holder identified: classified as usual
    ({}, 0, True, S.REPORTED),                    # another user's socket
    ({}, 1000, False, S.REPORTED),                # not listening
], ids=["unidentified", "identified", "another-owner", "not-listening"])
def test_a_listening_socket_the_launching_user_owns_whose_holder_cannot_be_identified_is_a_credential(
        monkeypatch, held, owner, listening, cls):
    """The designer's D-CS2-6: a listening socket the launching user owns, held by no process of the launching user's
    that the launcher can read (here a synthetic holder it cannot read), is a credential, marked so for row 2 and
    doctor; a socket whose holder is identified, another user's, or one that is not listening keeps its class."""
    path = "/home/u/tools/svc.sock"
    fake_host(monkeypatch, entries=[(5, path, listening)], listeners=held, stats={path: (0x0802, 50, owner)},
              unreadable=[] if held else [{"pid": 11, "name": "svc"}])
    got = S.inventory(control=CONTROL, env={})["candidates"]
    assert [(c["path"], c["class"], c.get("holder")) for c in got] == [
        (path, cls, S.UNIDENTIFIED if cls == S.CREDENTIAL else None)]


def test_a_listening_socket_is_judged_by_its_own_holder_whatever_else_the_table_lists_under_its_name(monkeypatch):
    """D-CS2-6 is decided per listening socket: another entry of the same name, held by a process the launcher can
    read (an accepted connection, or a second listener), never identifies its holder."""
    path = "/home/u/tools/svc.sock"
    for other in ((6, path, False), (6, path, True)):
        fake_host(monkeypatch, entries=[(5, path, True), other], listeners={6: "python3.11"},
                  stats={path: (0x0802, 50, 1000)})
        got = S.inventory(control=CONTROL, env={})["candidates"]
        assert [(c["class"], c.get("holder")) for c in got] == [(S.CREDENTIAL, S.UNIDENTIFIED)], other


@pytest.mark.skipif(sys.platform == "win32", reason="a symlink needs a privilege on Windows, and the host's paths "
                                                    "are POSIX where the inventory runs")
def test_the_resolved_spelling_comes_from_the_hosts_own_resolution(monkeypatch, tmp_path):
    """The resolved spelling of a listed path is the host's own (os.path.realpath of its directory), here on a link of
    the test's own; the other tests fake it."""
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    listed = str(tmp_path / "link" / "s.sock")
    fake_host(monkeypatch, entries=[(1, listed, True)], stats={listed: (0x0802, 60)})
    monkeypatch.setattr(S, "_realdir", REALDIR)
    got = S.inventory(control=CONTROL, env={})["candidates"]
    assert [c["real"] for c in got] == [{"path": os.path.join(os.path.realpath(real), "s.sock"), "fspath": None}]


def test_a_directory_the_launcher_cannot_list_is_recorded_unchecked_with_why(monkeypatch):
    """A listed path that is gone, in a directory the launcher cannot list, is recorded under unchecked with its
    class and the error; it is never dropped."""
    fake_host(monkeypatch, entries=[(1, "/home/other/cm/master.Xy12", True)],
              directories={"/home/other/cm": PermissionError(13, "Permission denied")})
    got = S.inventory(control=CONTROL, env={})
    assert got["unchecked"] == [{"path": "/home/other/cm/master.Xy12", "class": S.REPORTED,
                                 "error": "Permission denied"}]
    assert got["candidates"] == []
