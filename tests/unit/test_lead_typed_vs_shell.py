"""E231's typed-versus-shell measurement (``tools/perf/lead_typed_vs_shell.py``): its in-process parts."""

from __future__ import annotations

import math

import pytest

from aew.surface import mcp
from aew.surface.context import NORMAL
from tools.perf import lead_typed_vs_shell as E


@pytest.mark.parametrize("switches", [E.MESSAGING_ON, frozenset()], ids=["messaging-on", "messaging-off"])
def test_the_fixed_cost_is_the_pools_render_and_the_rows_sum_to_the_tool_list(switches):
    fixed = E.fixed_cost(switches)
    listing = mcp.tools_list(NORMAL, switches=switches)
    assert fixed["mcp"] == mcp.advertised_bytes(listing) and fixed["tools"] == len(listing["tools"])
    assert fixed["total"] == fixed["system"] + fixed["guide"] + fixed["join"] + fixed["mcp"]
    assert fixed["guide"] == len(fixed["guide_text"].encode("utf-8")) and fixed["join"] == 2
    shares = E.rows(switches)
    assert sum(shares.values()) - 1 + mcp.advertised_bytes({"tools": []}) == fixed["mcp"]


def test_a_core_and_pointers_guide_never_drops_a_kept_section_and_counts_its_table():
    guide = E.fixed_cost(E.MESSAGING_ON)["guide_text"]
    sections = dict(E.guide_sections(guide))
    for core in E.GUIDE_CORES.values():
        split = E.core_and_pointers(guide, core)
        kept = sum(size for heading, size in sections.items() if not heading or heading in core)
        assert split["sent_bytes"] == kept + split["toc_bytes"]
        assert split["saving_bytes"] == split["moved_bytes"] - split["toc_bytes"] > 0
    whole = E.core_and_pointers(guide, tuple(sections))
    assert whole["saving_bytes"] == 0 and whole["moved"] == []


def test_the_break_even_needs_a_shell_saving_per_use_to_exist():
    # Never: the shell costs no extra request and the typed result is the larger.
    assert E.break_even(600, 400, 34, 0.0, 40_000) == math.inf
    # A row that costs nothing on each request pays at once.
    assert E.break_even(0, 400, 34, 0.0, 40_000) == 0.0
    # 600 B on 34 requests against one saved 40,000 B request less 400 B resent on 16.5 later ones.
    assert E.break_even(600, 400, 34, 1.0, 40_000) == pytest.approx(600 * 34 / (40_000 - 400 * 16.5))


def test_the_fixture_keeps_the_hosts_environment_but_not_a_credential_git_or_a_desktop(tmp_path):
    # Windows' OpenSSL needs SYSTEMROOT to create a TLS context, which `aew init` does (#589's Windows lane).
    host = {"SYSTEMROOT": r"C:\Windows", "PATH": "/bin", "AEW_LEAD_TOKEN": "x", "aew_invocation_token": "y",
            "GIT_DIR": "/elsewhere", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/bus", "XDG_RUNTIME_DIR": "/run/user"}
    env = E.fixture_env(tmp_path, tmp_path / "home", host)
    assert env["SYSTEMROOT"] == r"C:\Windows" and env["PATH"] == "/bin" and env["HOME"] == str(tmp_path / "home")
    assert not {"AEW_LEAD_TOKEN", "aew_invocation_token", "GIT_DIR", "DBUS_SESSION_BUS_ADDRESS",
                "XDG_RUNTIME_DIR"} & set(env)
    assert env["GIT_AUTHOR_DATE"] == env["GIT_COMMITTER_DATE"]
