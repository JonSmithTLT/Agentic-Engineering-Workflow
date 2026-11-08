"""`aew doctor`'s read of the model list, without a server: a weaker read enters the register of weaker contexts as a
launch does, and its server is given the marker (G3 addendum 7; register E153). The sandbox, the process tree and the server are stood in for."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aew.harness import containment, model_list, procs
from aew.harness import weaker_register as W
from aew.harness.containment import netns
from aew.harness.opencode import adapter as A


class _Tree:
    def __init__(self, **_: Any) -> None:
        pass

    def kill(self) -> None:
        pass

    def survivors(self) -> list[int]:
        return []


def test_a_weaker_model_list_read_is_live_in_the_register_while_it_runs_and_its_server_carries_the_marker(
        tmp_path, monkeypatch):
    """The read goes through the launch's own `contain_launch`; a stand-in adapter sees what its server would get."""
    seen: list[dict[str, Any]] = []

    class Adapter(A.OpenCodeAdapter):
        def __init__(self, *_: Any) -> None:
            pass

        def read_model_list(self, contract: Any, agent_env: dict[str, str], *, until: float) -> dict[str, Any]:
            marker = Path(agent_env[W.MARKER])
            seen.append({"marker": marker, "label": json.loads(marker.read_text(encoding="utf-8")),
                         "live": [e["kind"] for e in W.read().live], "run_dir": Path(contract.run_dir)})
            return {"version": "stand-in", "complete": True, "empty": False, "models": []}

    weaker = containment.label(contained=False, reason="the execution policy allows weaker runs")
    monkeypatch.setattr(containment, "establish", lambda **kw: (None, weaker))
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")  # an owner that held the whole tree
    monkeypatch.setattr(netns, "provider_key_missing", lambda *a, **kw: None)
    monkeypatch.setattr(procs, "ProcessTree", _Tree)
    engine = SimpleNamespace(aew_root=tmp_path / ".aew", repo_root=tmp_path)
    pin = {"harness": "opencode", "provider": "fakeprov", "model": "fake-model"}
    out = model_list.read(engine, {}, pin, Adapter)
    [given] = seen
    assert out["complete"]
    assert given["marker"] == given["run_dir"] / "label.json" and given["label"] == weaker, "its marker names its label"
    assert "doctor_model_list" in given["live"], "entered before its server started"
    assert "doctor_model_list" not in [e["kind"] for e in W.read().live], "ended once the read returned"
    [ended] = [json.loads(f.read_text(encoding="utf-8")) for f in W.root().glob("doctor_model_list-*.json")]
    assert ended["outcome"] == "clean"
    assert not given["run_dir"].exists()
