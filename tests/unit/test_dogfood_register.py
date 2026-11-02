"""The dogfood's agent contexts each enter the register of weaker contexts while they run (G3 addendum 7; #321
review, F1 and F5): its raw arm, its Lead's debrief and its hidden scorer, each with no sandbox. Each is driven with
its OpenCode session or its scorer stood in for, and reads the register as its first process would start."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aew.harness import weaker_register as W
from aew.harness.opencode import projection

DOGFOOD = Path(__file__).resolve().parents[2] / "eval" / "m3" / "dogfood"


@pytest.fixture
def dogfood(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(DOGFOOD))
    import dogfood as module

    monkeypatch.setattr(W, "scan", lambda proc=None, uid=None: None)  # the host's own processes are not this test's
    monkeypatch.setattr(module.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    monkeypatch.setattr(module, "profile_of", lambda model: {"provider": "fakeprov", "model": "fake-model"})
    monkeypatch.setattr(module, "provider_env", lambda profile: [])
    monkeypatch.setattr(module, "scan_secrets", lambda where, secret: {})
    monkeypatch.setattr(module, "git", lambda repo, *args: "")  # its check that the real checkout stayed untouched
    return module


@pytest.fixture
def session(monkeypatch, tmp_path):
    """The headless OpenCode session, stood in for: what the register held, and the marker its server was given, when
    the session started."""
    seen: dict = {}

    class Session:
        def __init__(self, state: Path) -> None:
            self.state_dir = state
            self.tree = SimpleNamespace(survivors=lambda wait_s=10.0: [])

        def _started(self, env: dict) -> None:
            seen.update(live=[(x["kind"], x["why"]) for x in W.read().live], marker=env.get(W.MARKER))

        def open(self, *, env: dict, **_: object) -> None:
            self._started(env)

        def resume(self, *, env: dict, **_: object) -> None:
            self._started(env)

        def say(self, text: str) -> None:
            pass

        def wait_turn(self, deadline: float, over_cap: object) -> str:
            return "idle"

        def live_usage(self) -> dict:
            return {}

        def close(self) -> dict:
            return {}

    stub = SimpleNamespace(HeadlessSession=Session, raw_config=lambda profile, steps: {}, shell_env=lambda env: {},
                           lead_config=lambda *a, **k: ({"agents": {projection.LEAD_AGENT: {}}}, None),
                           assistant_steps=lambda state: 0, command_log=lambda state: [],
                           last_text=lambda state, after: "")
    monkeypatch.setitem(sys.modules, "headless", stub)
    return seen


def test_the_dogfoods_raw_arm_is_live_in_the_register_while_its_model_runs(dogfood, session, monkeypatch, tmp_path):
    monkeypatch.setattr(dogfood, "build_repo", lambda task, repo, with_seed: repo.mkdir(parents=True) or "base")
    monkeypatch.setattr(dogfood, "hidden", lambda task, repo: {})
    monkeypatch.setattr(dogfood, "changed_paths", lambda *a: [])
    monkeypatch.setattr(dogfood, "session_summary", lambda s, key: {})
    monkeypatch.setattr(dogfood, "totals", lambda record, key: {})
    dogfood.run(sorted(dogfood.TASKS)[0], "raw", "fakeprov/fake-model", {}, 1.0, tmp_path / "results.jsonl")
    assert session["live"] == [("eval_raw", "running")] and session["marker"]
    assert W.read().live == [], "it ends when the session's processes are proven ended"


def test_the_dogfoods_debrief_is_live_in_the_register_while_its_model_answers(dogfood, session, monkeypatch,
                                                                              tmp_path):
    from aew.engine import api

    work = tmp_path / "T1-aew-1"
    db = work / "lead" / "lead-1" / "harness" / "xdg-data" / "opencode" / "opencode.db"
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.execute("create table session_v2 (id text, permission text)")
    con.execute("insert into session_v2 values ('ses_1', '[]')")
    con.commit()
    con.close()
    results = tmp_path / "results.jsonl"
    results.write_text(json.dumps({"workdir": str(work), "model": "fakeprov/fake-model", "task": "T1",
                                   "lead_guide": "none"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(dogfood, "DEBRIEF_ROOT", tmp_path / "debrief")
    monkeypatch.setattr(api.Engine, "discover", staticmethod(lambda root: SimpleNamespace(lead_guide=lambda: "")))
    dogfood.debrief_run(work.name, results, tmp_path / "debriefs.jsonl")
    assert session["live"] == [("dogfood_debrief", "running")] and session["marker"]
    assert W.read().live == []


def test_the_dogfoods_hidden_scorer_is_live_in_the_register_while_it_scores(dogfood, monkeypatch, tmp_path):
    seen: dict = {}

    def scorer(argv, *, env, **_):
        seen.update(live=[(x["kind"], x["why"]) for x in W.read().live], marker=env.get(W.MARKER))
        return SimpleNamespace(stdout=json.dumps({"passed": True}), stderr="", returncode=0)

    monkeypatch.setattr(dogfood.subprocess, "run", scorer)
    assert dogfood.hidden("T1", tmp_path) == {"passed": True}
    assert seen["live"] == [("dogfood_scorer", "running")] and seen["marker"]
