"""The socket inventory (STG-05 CB-03; the designer's D-CS2-2 and D-CS2-3): what fails a launch, what is the run's own,
what is only reported, and how the kernel's socket table becomes the paths a sandbox is checked for.

Pure: every input is synthetic (names, table text, stat results, mount tables), nothing binds a socket, so it runs on
every platform. The real self-test on a real host is in tests/integration/test_containment.py.
"""

from __future__ import annotations

import stat
from types import SimpleNamespace

import pytest

from aew.harness.containment import sockets as S

# One planted path per row of the table, and the class it must get (the hand-off's list and the Lead's rulings).
PLANTED = {
    S.DISPLAY: ["/tmp/.X11-unix/X0", "/run/user/1000/wayland-0"],
    S.APPROVAL: ["/run/aew-g3/approve.sock", "/run/aew-g3/store/deep/s.sock"],
    S.AEW_SERVICE: ["/run/aew-wis/issuer.sock", "/run/aew-owner/store/owner.sock", "/tmp/aew-bridge-x/s"],
    S.CREDENTIAL: ["/tmp/ssh-XXXX/agent.1234", "/home/u/.gnupg/S.gpg-agent", "/run/user/1000/gnupg/S.gpg-agent.ssh",
                   "/run/user/1000/gnupg/S.scdaemon", "/home/u/.gnupg/S.keyboxd",
                   "/home/u/.cache/git/credential/socket", "/home/u/.git-credential-cache/socket",
                   "/run/user/1000/keyring/control", "/run/user/1000/bus"],
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
    path.write_text(TABLE_TEXT)
    entries = S.table(str(path))
    assert [(e.inode, e.name, e.listening) for e in entries] == [
        (101, "/home/u/.cache/svc/listen.sock", True), (102, "/home/u/.cache/svc/listen.sock", False),
        (103, "@/tmp/.X11-unix/X0", True), (104, "relative.sock", True), (106, "/srv/with space/s.sock", True)]


def test_an_unreadable_table_raises_for_the_caller_to_fail_closed(tmp_path):
    with pytest.raises(OSError):
        S.table(str(tmp_path / "absent"))


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
    ("systemd", S.ESCAPE), ("python3.11", None), ("sshd", None), (None, None),
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


def fake_host(monkeypatch, *, entries, listeners=None, stats=None, directories=None, mounts=()):
    """The inventory's host inputs, all synthetic: the table's entries, the launching user's listeners
    {inode: executable}, lstat results {path: (dev, ino) or an exception}, directory listings {dir: [(path, dev,
    ino)] or an exception}, and the host's mount table."""
    def stat_of(dev: int, ino: int) -> SimpleNamespace:
        return SimpleNamespace(st_mode=SOCK, st_dev=dev, st_ino=ino)

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
    monkeypatch.setattr(S, "listeners", lambda inodes: {i: x for i, x in (listeners or {}).items() if i in inodes})
    monkeypatch.setattr(S, "mounts", lambda path=S.MOUNTINFO: list(mounts))
    monkeypatch.setattr(S, "_stat", lstat)
    monkeypatch.setattr(S, "_socket_files", socket_files)
    monkeypatch.setattr(S, "_majmin", lambda dev: f"{dev >> 8}:{dev & 0xff}")


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
