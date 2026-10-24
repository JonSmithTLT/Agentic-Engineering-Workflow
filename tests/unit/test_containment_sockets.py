"""The socket inventory's classes (STG-05 CB-03): what fails a launch, what is the run's own, what is only reported.

Pure: the paths are planted names, nothing binds a socket, so it runs on every platform. The walk itself, with real
sockets on a real host, is in tests/integration/test_containment.py.
"""

from __future__ import annotations

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
            "/home/u/.aew-test-tmp/contain-1/s.sock", "/home/u/AEW-web/dev.sock"]


@pytest.mark.parametrize("cls", sorted(PLANTED))
def test_each_failing_class_matches_its_planted_paths_and_nothing_else(cls):
    assert cls in S.FAILING
    got = {p: S.classify(p, env={}) for p in PLANTED[cls]}
    assert got == dict.fromkeys(PLANTED[cls], cls)
    assert all(S.classify(p, env={}) != cls for other, paths in PLANTED.items() if other != cls for p in paths)


def test_an_unlisted_socket_is_reported_not_refused():
    """A site's ordinary services never block a run (SSSD's pipes): reported, not failing. A directory named like
    AEW's own but not lower-case `aew-<service>` is not AEW's (the operator's checkouts are `AEW-<topic>`)."""
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


def test_the_runs_own_bridge_socket_is_its_own_never_a_failure():
    own = ("/tmp/aew-bridge-abc",)
    assert S.classify("/tmp/aew-bridge-abc/s", own=own, env={}) == S.OWN
    assert S.classify("/tmp/aew-bridge-other/s", own=own, env={}) == S.AEW_SERVICE  # another run's bridge
