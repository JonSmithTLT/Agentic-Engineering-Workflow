"""F9-A MS0: the OpenCode 2.0.18 live-delivery probe. One case, one private server, one scripted fake model.

Usage: ``python probe.py OUT CASE REP`` (``python probe.py --list`` prints the cases). ``OUT`` is a directory outside
the checkout; the run is written to ``OUT/<case>-<rep>/``. Run it by hand, case by case (``run_case.sh`` on Windows,
``run_linux.sh`` on Linux); nothing collects it (``tests/live`` needs ``--live``, and this directory holds no test
module). The results it produced are ADR-0017 D8's evidence,
``docs/implementation/adr/evidence/f9a-delivery-probe-2026-10-10/``.

**The departure from MS0's plan, recorded** (F9-A plan v4, amendment 1, A9): MS0 specified a free model through
``AEW_LIVE_ROUTING``. This probe uses a scripted fake OpenAI-compatible model on loopback instead (``fake_model.py``),
by the plan owner's brief: no provider spend or credential, and deterministic slow steps. The mechanics and timings it
measures are OpenCode's own. It leaves unmeasured how a real model responds to D-23's framing (P6), and how it spends
the steps a queued input waits behind. MS7's live check (``test_live_a_steer_message_is_admitted_at_the_next_boundary``)
covers steer's mechanics with a real model.

How it runs. It imports the installed ``aew`` (run it with the interpreter of an environment where AEW is installed):

- AEW's production ``OpenCodeAdapter`` launches the run: its ``ProcessTree`` (a Windows job, ``CREATE_NO_WINDOW``) or
  POSIX process group, ``server_env``, ``Server.start``, the health and capability probe, the pinned-model and
  projection checks, the session body, the curated session environment, ``EventStream``, its watcher (``_poll``) and
  the launch contract as the first prompt. The only change is one custom provider, ``probe``
  (``@ai-sdk/openai-compatible`` at the in-process fake model on 127.0.0.1, placeholder key), added to the projected
  configuration by wrapping ``projection.invocation_config``.
- The binary is ``AEW_OPENCODE_BIN`` when the caller sets it, else ``adapter.default_binary()``; the server's
  ``/api/info`` must report 2.0.18, or the run stops.
- The environment is scrubbed first: every ``*_API_KEY``, ``*_TOKEN``, ``OPENAI*``, ``OPENCODE*``, ``AEW_*`` and proxy
  variable (and ``SHELL``) is dropped from this process, so ``server_env`` cannot pass one on. ``NO_PROXY`` covers
  loopback, and urllib gets an empty ``ProxyHandler``.
- **Lead inputs use a raw-post mode** (until MS5): ``POST /api/session/{id}/prompt`` with the chosen ``id``,
  ``delivery``, ``metadata`` and ``resume``, after the same bookkeeping ``_prompt`` does (so the adapter's watcher waits
  for them). MS5 switches every case to post through ``adapter.deliver``, so that the probe measures the shipped code;
  the raw-post mode then stays only for the P5 cases (re-posts, ids that conflict, malformed ids), which ``deliver``
  must never send. ``adapter.interrupt`` is the production call wherever a case interrupts.
- Recorded per run: ``events.jsonl`` (every event-stream frame, wall time), ``model.jsonl`` (every model request and
  answer), ``posts.jsonl`` (every POST: status and full body), ``deliveries.jsonl`` (REST 404 -> 200 per posted id,
  polled every 0.2 s), ``adapter.jsonl`` (the adapter's own telemetry), ``messages.json``, ``result.json``,
  ``server.log``, the step marker files (shell start and end, epoch ms). These raw files carry host paths and are never
  committed: ``summarize.py``, ``table.py`` and ``p5_table.py`` reduce them to the committed evidence.

Only processes this script started are ever stopped, through their own handles (the server's ``Popen``, or the run's
own ``ProcessTree``). Run one OpenCode server at a time.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from collections.abc import Callable
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

# The binary the caller chose, read before the scrub below drops every AEW_* variable.
_CONFIGURED_BIN = os.environ.get("AEW_OPENCODE_BIN")

# No credential and no proxy may reach anything this process starts.
for _k in list(os.environ):
    _u = _k.upper()
    if (_u.endswith("_API_KEY") or _u.endswith("_TOKEN") or _u.startswith("OPENAI") or _u.startswith("OPENCODE")
            or "PROXY" in _u or _u == "SHELL" or _u.startswith("AEW_")) and not _u.startswith("AEW_PROBE_"):
        del os.environ[_k]
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

# fake_model is a sibling module: a script's own directory is first on sys.path.
import fake_model  # noqa: E402

import aew  # noqa: E402
from aew.harness.contract import LaunchContract  # noqa: E402
from aew.harness.opencode import adapter as oc_adapter  # noqa: E402
from aew.harness.opencode import projection  # noqa: E402
from aew.harness.opencode.adapter import OpenCodeAdapter, new_message_id, server_env  # noqa: E402
from aew.harness.opencode.client import OpenCodeError, OpenCodeUnavailable, Server  # noqa: E402
from aew.harness.procs import ProcessTree  # noqa: E402

WINDOWS = sys.platform == "win32"
VERSION = "2.0.18"
_bin = Path(_CONFIGURED_BIN) if _CONFIGURED_BIN else oc_adapter.default_binary()
if _bin is None or not _bin.exists():
    raise SystemExit("no OpenCode binary: set AEW_OPENCODE_BIN to the OpenCode 2.0.18 CLI")
BIN: Path = _bin
os.environ[oc_adapter.BIN_ENV] = str(BIN)  # the adapter's own lookup; the served version is checked at launch
PLACEHOLDER_KEY = "placeholder-not-a-real-key"
PORT: dict[str, int] = {}
CURRENT: dict[str, Any] = {}

_orig_config = projection.invocation_config


def _with_probe_provider(*a: Any, **k: Any) -> dict[str, Any]:
    cfg = _orig_config(*a, **k)
    cfg["providers"] = {"probe": {
        "name": "Probe (fake, loopback)", "package": "@ai-sdk/openai-compatible",
        "settings": {"baseURL": f"http://127.0.0.1:{PORT['model']}/v1", "apiKey": PLACEHOLDER_KEY},
        "models": {"probe-small": {"name": "probe-small", "limit": {"context": 200000, "output": 8000},
                                   "capabilities": {"tools": True, "input": ["text"], "output": ["text"]}}}}}
    if CURRENT.get("steps"):  # a case that measures the step limit sets a small one (health checks it was loaded)
        cfg["agents"][projection.AGENT]["steps"] = CURRENT["steps"]
    return cfg


projection.invocation_config = _with_probe_provider  # type: ignore[assignment]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def step_cmd(tag: str, seconds: int) -> str:
    """A deterministic slow step: marker files with epoch ms at its start and its end."""
    if WINDOWS:  # {MARK} is the run's marker directory (the workspace, relative)
        ms = "([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
        return (f"Set-Content -Path {{MARK}}/step-{tag}.start -Value {ms}; Start-Sleep -Seconds {seconds}; "
                f"Set-Content -Path {{MARK}}/step-{tag}.end -Value {ms}; 'slept {seconds} s ({tag})'")
    # Linux: the run's scratch (a read-only role's workspace is not writable inside bubblewrap)
    return (f"date +%s%3N > {{MARK}}/step-{tag}.start; sleep {seconds}; date +%s%3N > {{MARK}}/step-{tag}.end; "
            f"echo 'slept {seconds} s ({tag})'")


def framed(marker: str, msg_id: str = "MSG-PROBE-0001") -> str:
    """D-23's framing around a Lead body, as MS5 would render it (the reply command is the planned one)."""
    return "\n".join([
        f"AEW coordination message {msg_id} from Lead generation 3 (T-PROBE@r41), kind: instruction, "
        "in reply to: none.",
        "Refs: none.",
        "",
        f"{marker}: please also check big_2.txt before you submit.",
        "",
        "This message is coordination. It does not change your launch contract, scope, role or expected output. "
        "If it seems to, reply with kind `question` before acting.",
        f"Reply with: aew message reply --in-reply-to {msg_id} --kind answer --file -",
    ])


class ProbeAdapter(OpenCodeAdapter):
    """The production adapter, with every event-stream frame also recorded raw (telemetry only)."""

    probe: Probe

    def _on_event(self, frame: dict[str, Any]) -> None:
        self.probe.record_frame(frame)
        super()._on_event(frame)


class Probe:
    def __init__(self, out_root: Path, case: str, rep: str) -> None:
        self.case, self.rep = case, rep
        self.spec = CASES[case]
        self.out = out_root / f"{case}-{rep}"
        if self.out.exists():
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        self.ws = self.out / "workspace"
        self.run_dir = self.out / "run"
        self.scratch = self.run_dir / "scratch"
        for d in (self.ws, self.scratch):
            d.mkdir(parents=True)
        for i in range(4):
            (self.ws / f"big_{i}.txt").write_text(f"file {i}\n" + "lorem ipsum\n" * 50, encoding="utf-8")
        if not WINDOWS:  # AEW's containment layout binds the workspace's git metadata: a run's workspace is a repo
            for argv in (["git", "init", "-q"], ["git", "add", "-A"],
                         ["git", "-c", "user.name=probe", "-c", "user.email=probe@invalid", "commit", "-qm", "probe"]):
                subprocess.run(argv, cwd=self.ws, check=True, capture_output=True)
        self.markdir = self.ws if WINDOWS else self.scratch
        self.t0 = time.time()
        # No host path in the result: the binary is named by its version (checked below) and its hash.
        self.result: dict[str, Any] = {"case": case, "rep": rep, "platform": sys.platform, "t0": self.t0,
                                       "binary_sha256": sha256_of(BIN), "aew_version": aew.__version__,
                                       "notes": []}
        self.frames: list[dict[str, Any]] = []
        self.cond = threading.Condition()
        self.files = {n: open(self.out / f"{n}.jsonl", "a", encoding="utf-8")  # closed in run()
                      for n in ("events", "posts", "deliveries", "adapter", "marks")}
        self.flock = threading.Lock()
        self.stop = threading.Event()
        self.watchers: list[threading.Thread] = []
        self.layout: Any = None
        self.extra_servers: list[Server] = []
        self.extra_trees: list[ProcessTree] = []

    # ------------------------------------------------------------------ recording

    def rel(self, t: float | None = None) -> float:
        return round((time.time() if t is None else t) - self.t0, 3)

    def write(self, name: str, rec: dict[str, Any]) -> None:
        with self.flock:
            self.files[name].write(json.dumps(rec, default=str) + "\n")
            self.files[name].flush()

    def mark(self, what: str, **kw: Any) -> None:
        self.write("marks", {"t": time.time(), "s": self.rel(), "mark": what, **kw})

    def record_frame(self, frame: dict[str, Any]) -> None:
        t = time.time()
        rec = {"t": t, "s": self.rel(t), **frame}
        with self.cond:
            self.frames.append(rec)
            self.cond.notify_all()
        self.write("events", rec)

    def emit(self, rec: dict[str, Any]) -> None:
        self.write("adapter", {"t": time.time(), "s": self.rel(), **rec})

    # ------------------------------------------------------------------ helpers for case drivers

    def wait_event(self, kind: str, pred: Callable[[dict[str, Any]], bool] | None = None, timeout: float = 60,
                   after: int = 0) -> dict[str, Any] | None:
        end = time.time() + timeout
        with self.cond:
            i = after
            while True:
                while i < len(self.frames):
                    f = self.frames[i]
                    i += 1
                    if f.get("type") == kind and (pred is None or pred(f.get("data") or {})):
                        return f
                left = end - time.time()
                if left <= 0:
                    return None
                self.cond.wait(left)

    def n_frames(self) -> int:
        with self.cond:
            return len(self.frames)

    def wait_file(self, name: str, timeout: float = 60) -> float | None:
        end = time.time() + timeout
        p = self.markdir / name
        while time.time() < end:
            if p.exists():
                try:
                    return int(p.read_text(encoding="utf-8-sig").strip()) / 1000.0
                except (ValueError, OSError):  # still being written (Windows locks it meanwhile)
                    pass
            time.sleep(0.05)
        return None

    def wait_in_flight(self, timeout: float = 60) -> bool:
        return self.model_state.in_flight.wait(timeout)

    def post(self, text: str, *, delivery: str | None = None, mid: str | None = None,
             metadata: dict[str, Any] | None = None, resume: bool | None = None, track: bool = True,
             session: str | None = None, label: str = "") -> dict[str, Any]:
        """One Lead input in the raw-post mode, as D-28's ``deliver`` would post it (with ``_prompt``'s watcher
        bookkeeping). MS5 replaces it with ``adapter.deliver`` for every case but P5's."""
        ad = self.adapter
        mid = mid or new_message_id()
        sid = session or ad.session
        if track and sid == ad.session:
            with ad._lock:
                if mid not in ad.sent:
                    ad.sent.append(mid)
                if ad.turn != "ended":
                    ad.turn = "running"
                ad._idle_seen = None
        body: dict[str, Any] = {"id": mid, "text": text}
        if delivery:
            body["delivery"] = delivery
        if metadata is not None:
            body["metadata"] = metadata
        if resume is not None:
            body["resume"] = resume
        t_send = time.time()
        rec: dict[str, Any] = {"label": label, "id": mid, "session": sid, "request": body, "t_send": t_send,
                               "s_send": self.rel(t_send), "turn_before": ad.inspect()["turn"]}
        try:
            resp = ad.client.post(f"/api/session/{sid}/prompt", body)
            rec.update({"status": 200, "response": resp})
        except OpenCodeError as exc:
            rec.update({"status": exc.status, "response": exc.body})
        except OpenCodeUnavailable as exc:
            rec.update({"status": None, "response": str(exc)})
        rec["t_resp"] = time.time()
        rec["s_resp"] = self.rel(rec["t_resp"])
        self.write("posts", rec)
        ad._wake.set()
        if rec["status"] == 200 and sid == ad.session:
            self.watch_delivery(mid, label)
        return rec

    def watch_delivery(self, mid: str, label: str = "", timeout: float = 900) -> None:
        sid = self.adapter.session

        def run() -> None:
            n404 = 0
            other: list[Any] = []
            end = time.time() + timeout
            while not self.stop.is_set() and time.time() < end:
                try:
                    self.adapter.client.get(f"/api/session/{sid}/message/{mid}")
                    t = time.time()
                    self.write("deliveries", {"id": mid, "label": label, "t_200": t, "s_200": self.rel(t),
                                              "n404": n404, "other": other[:5]})
                    return
                except OpenCodeError as exc:
                    if exc.status == 404:
                        n404 += 1
                    else:
                        other.append(exc.status)
                except OpenCodeUnavailable as exc:
                    other.append(str(exc)[:80])
                    if not self.adapter.server or not self.adapter.server.alive():
                        break
                time.sleep(0.2)
            self.write("deliveries", {"id": mid, "label": label, "t_200": None, "n404": n404, "other": other[:5],
                                      "gave_up": True})

        th = threading.Thread(target=run, daemon=True)
        th.start()
        self.watchers.append(th)

    def wait_turn(self, states: tuple[str, ...] = ("ended",), timeout: float = 120) -> str:
        end = time.time() + timeout
        while time.time() < end:
            turn = self.adapter.inspect()["turn"]
            if turn in states:
                self.mark("turn", turn=turn, inspect=self.adapter.inspect())
                return turn
            time.sleep(0.1)
        self.mark("turn-timeout", inspect=self.adapter.inspect())
        return "timeout"

    def state(self, label: str = "") -> dict[str, Any]:
        """The REST view of the session now: active, inbox, newest message."""
        c, sid = self.adapter.client, self.adapter.session
        out: dict[str, Any] = {"label": label, "s": self.rel()}
        try:
            out["active"] = sid in ((c.get("/api/session/active") or {}).get("data") or {})
            out["inbox"] = [{"id": i.get("id"), "delivery": i.get("delivery"), "type": i.get("type"),
                             "text": ((i.get("payload") or {}).get("text") or "")[:60]}
                            for i in (c.get(f"/api/session/{sid}/inbox") or {}).get("data") or []]
            newest = (c.get(f"/api/session/{sid}/message", {"order": "desc", "limit": "1"}) or {}).get("data") or []
            out["newest"] = {k: (newest[0] if newest else {}).get(k) for k in ("type", "id", "outcome")}
        except (OpenCodeError, OpenCodeUnavailable) as exc:
            out["error"] = str(exc)[:300]
        self.mark("state", **out)
        return out

    def wait_raw_idle(self, timeout: float = 60, settle: float = 1.0) -> dict[str, Any]:
        """For a session the adapter no longer watches: not active, inbox empty, newest message idle, twice."""
        end = time.time() + timeout
        prev = None
        while time.time() < end:
            st = self.state("raw-idle-poll")
            ok = (not st.get("active")) and not st.get("inbox") and (st.get("newest") or {}).get("type") == "idle"
            if ok and prev == (st.get("newest") or {}).get("id"):
                return st
            prev = (st.get("newest") or {}).get("id") if ok else None
            time.sleep(settle)
        return {"timeout": True}

    def sleep(self, s: float) -> None:
        time.sleep(s)

    # ------------------------------------------------------------------ the run

    def contract(self) -> LaunchContract:
        pack = "\n".join(["# Work pack (probe)", "", "Probe for live delivery: follow the steps; say done."])
        return LaunchContract(
            run="R-PROBE-0001", invocation="I-PROBE-0001", work_unit="T-PROBE", role="investigator", scope="probe",
            card={"id": "investigator"}, execution_profile={"provider": "probe", "model": "probe-small"},
            workspace=str(self.ws), expected_kinds=["investigation_report"], operations=[], pack_path="pack.md",
            pack_sha256="0" * 64, pack_text=pack, continuation=None, run_dir=str(self.run_dir), extra={},
            scratch=str(self.scratch))

    def agent_env(self) -> dict[str, str]:
        if WINDOWS:
            keep = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
            env = {k: os.environ[k] for k in os.environ if k.upper() in keep}
            env.update({"TEMP": str(self.scratch), "TMP": str(self.scratch)})
            return env
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.scratch),
               "TMPDIR": str(self.scratch), "LANG": "C.UTF-8"}
        if self.layout is not None:
            env.update(self.layout.env)
        return env

    def run(self) -> dict[str, Any]:
        spec = self.spec
        CURRENT.clear()
        CURRENT.update(spec)
        mark = "." if WINDOWS else str(self.markdir)
        script = json.loads(json.dumps(spec["script"]).replace("{MARK}", mark))
        st = fake_model.State({"script": script}, str(self.out / "model.jsonl"))
        self.model_state = st
        handler = type("H", (fake_model.Handler,), {"st": st})
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        srv.daemon_threads = True
        PORT["model"] = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.result["model_port"] = PORT["model"]
        if not WINDOWS and os.environ.get("AEW_PROBE_BWRAP") == "1":  # AEW's own run containment (bubblewrap)
            from aew.harness.containment.layout import for_run
            self.layout = for_run(role="investigator", scope="probe", workspace=self.ws, run_dir=self.run_dir,
                                  scratch=self.scratch, bridge_dir=None, policy=None)
            self.result["contained"] = True
        self.tree = ProcessTree(self.layout) if self.layout is not None else ProcessTree()
        ad = ProbeAdapter(self.tree, self.run_dir, self.emit)
        ad.probe = self
        self.adapter = ad
        driver_error = None
        try:
            t = time.time()
            launched = ad.launch(self.contract(), self.agent_env())
            self.result["launch_s"] = round(time.time() - t, 3)
            self.result["version"] = launched.get("version")
            self.result["session"] = launched.get("session")
            if launched.get("version") != VERSION:
                raise SystemExit(f"wrong OpenCode version {launched.get('version')}")
            self.mark("launched", session=ad.session)
            self.watch_delivery(ad.sent[0], "contract")
            try:
                spec["driver"](self)
            except Exception as exc:  # record and shut down
                driver_error = f"{type(exc).__name__}: {exc}"
                self.result["driver_traceback"] = traceback.format_exc()
            self.result["driver_error"] = driver_error
            self.result["inspect"] = ad.inspect()
            if ad.server is not None and ad.server.alive():
                self.dump()
        except BaseException as exc:
            self.result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            end = time.time() + 3  # let the delivery watchers see a last-moment delivery
            for th in self.watchers:
                th.join(max(0.0, end - time.time()))
            self.stop.set()
            try:
                self.result["collect"] = ad.collect()
            except Exception as exc:
                self.result["collect_error"] = str(exc)[:300]
            t = time.time()
            ad.terminate()  # the lease (stdin EOF), as the supervisor does
            proc = ad.server.proc if ad.server else None
            self.result["lease_close"] = {"exit_code": proc.poll() if proc else None, "s": round(time.time() - t, 3)}
            for extra in self.extra_servers:
                if extra.alive():
                    extra.close(wait_s=5)
            self.tree.kill()  # the run's own job / process group: whatever the run started
            for extra_tree in self.extra_trees:
                extra_tree.kill()
            srv.shutdown()
            for f in self.files.values():
                f.close()
            log = self.run_dir / "harness" / "server.log"
            if log.exists():
                shutil.copy(log, self.out / "server.log")
            self.result["elapsed_s"] = self.rel()
            (self.out / "result.json").write_text(json.dumps(self.result, indent=1, default=str), encoding="utf-8")
        return self.result

    def dump(self) -> None:
        c, sid = self.adapter.client, self.adapter.session
        msgs: list[dict[str, Any]] = []
        params = {"order": "asc", "limit": "200"}
        for _ in range(20):
            page = c.get(f"/api/session/{sid}/message", params) or {}
            msgs += page.get("data") or []
            nxt = (page.get("cursor") or {}).get("next")
            if not nxt:
                break
            params = {"cursor": str(nxt), "limit": "200"}
        (self.out / "messages.json").write_text(json.dumps(msgs, indent=1), encoding="utf-8")
        self.result["final_state"] = self.state("final")
        self.result["session_info"] = (c.get(f"/api/session/{sid}") or {}).get("data")


# ---------------------------------------------------------------------- case drivers

def d_queue_shell(delivery: str) -> Callable[[Probe], None]:
    def drive(p: Probe) -> None:
        start = p.wait_file("step-a.start", 60)
        p.mark("step-start", t=start)
        p.sleep(5)
        p.post("LEADMSG-Q1: Lead note during the shell step.", delivery=delivery, label="Q1")
        p.state("after-post")
        p.wait_turn(timeout=120)
    return drive


def d_queue_model(delivery: str) -> Callable[[Probe], None]:
    def drive(p: Probe) -> None:
        if not p.wait_in_flight(60):
            raise RuntimeError("the delayed model call never started")
        p.mark("model-call-in-flight")
        p.sleep(4)
        p.post("LEADMSG-Q1: Lead note during the model call.", delivery=delivery, label="Q1")
        p.state("after-post")
        p.wait_turn(timeout=120)
    return drive


def d_closing_inflight(p: Probe, delivery: str = "queue") -> None:
    if not p.wait_in_flight(60):
        raise RuntimeError("the delayed final model call never started")
    p.mark("final-call-in-flight")
    p.sleep(3)
    p.post("LEADMSG-C1: Lead note during the final model call.", delivery=delivery, label="C1")
    p.wait_turn(timeout=120)


def d_closing_after(p: Probe) -> None:
    f = p.wait_event("session.execution.succeeded", timeout=60)
    p.mark("execution-succeeded-seen", frame_s=f and f["s"], turn=p.adapter.inspect()["turn"])
    rec = p.post("LEADMSG-C2: Lead note just after the turn's last step.", delivery="queue", label="C2")
    p.mark("posted-after-succeeded", turn_before=rec["turn_before"])
    p.wait_turn(timeout=60)
    p.state("end")


def d_held(p: Probe, delivery: str = "queue") -> None:
    start = p.wait_file("step-a.start", 60)
    p.mark("step-start", t=start)
    p.sleep(3)
    p.adapter.interrupt()  # production: POST /interrupt?resume=false
    p.mark("interrupted")
    turn = p.wait_turn(("held", "ended"), timeout=30)
    p.mark("after-interrupt", turn=turn)
    p.sleep(2)
    p.state("held")
    p.post("LEADMSG-H1: staged with resume false while held.", delivery=delivery, resume=False, track=False,
           label="H1")
    p.sleep(8)
    p.state("8s-after-H1")
    p.post("LEADMSG-H2: posted with resume default while held.", delivery=delivery, label="H2")
    p.wait_turn(timeout=90)
    p.state("end")


def d_idle_noresume(p: Probe, delivery: str = "queue") -> None:
    p.wait_turn(timeout=60)
    p.sleep(1)
    p.state("idle")
    n = p.n_frames()
    p.post("LEADMSG-R1: staged with resume false on an idle session.", delivery=delivery, resume=False,
           track=False, label="R1")
    p.sleep(8)
    started = p.wait_event("session.execution.started", timeout=0.1, after=n)
    p.mark("8s-after-R1", execution_started=bool(started))
    p.state("8s-after-R1")
    p.post("LEADMSG-R2: posted with resume default on the idle session.", delivery=delivery, track=False,
           label="R2")
    p.wait_raw_idle(timeout=60)


def d_busy_noresume(p: Probe) -> None:
    start = p.wait_file("step-a.start", 60)
    p.mark("step-start", t=start)
    p.sleep(3)
    p.post("LEADMSG-B1: resume false while the session is busy.", delivery="queue", resume=False, track=False,
           label="B1")
    p.wait_turn(timeout=90)
    p.sleep(3)
    p.state("end")


def d_ordering(seq: list[tuple[str, str]]) -> Callable[[Probe], None]:
    def drive(p: Probe) -> None:
        start = p.wait_file("step-a.start", 60)
        p.mark("step-start", t=start)
        p.sleep(2)
        for tag, delivery in seq:
            p.post(f"LEADMSG-{tag}: ordering probe ({delivery}).", delivery=delivery, label=tag)
        p.state("after-posts")
        p.wait_turn(timeout=120)
    return drive


def d_duplicate(p: Probe) -> None:
    """P5. These posts stay raw for good: ``deliver`` must never re-post, conflict or send a malformed id."""
    start = p.wait_file("step-a.start", 60)
    p.mark("step-start", t=start)
    p.sleep(2)
    x = new_message_id()
    p.post("LEADMSG-D1: first post of id X.", delivery="queue", mid=x, label="X-1")
    p.post("LEADMSG-D1: first post of id X.", delivery="queue", mid=x, label="X-2-same")
    p.post("LEADMSG-D2: id X again, different text and steer.", delivery="steer", mid=x, label="X-3-changed")
    p.state("after-dups-queued")
    p.wait_turn(timeout=90)
    p.sleep(1)
    n = p.n_frames()
    p.post("LEADMSG-D1: first post of id X.", delivery="queue", mid=x, track=False, label="X-4-after-delivery")
    p.sleep(6)
    started = p.wait_event("session.execution.started", timeout=0.1, after=n)
    p.mark("6s-after-X-4", execution_started=bool(started))
    p.state("after-X-4")
    # 409s for other causes.
    c, ad = p.adapter.client, p.adapter
    body = projection.session_body(ad.contract, ad.directory, json.loads(
        (p.run_dir / "harness" / "opencode-config.json").read_text(encoding="utf-8"))["permissions"])
    sid2 = str(c.post("/api/session", body)["data"]["id"])
    p.mark("second-session", session=sid2)
    p.post("LEADMSG-D3: id X posted to another session.", delivery="queue", mid=x, track=False, session=sid2,
           label="X-5-other-session")
    msgs = (c.get(f"/api/session/{ad.session}/message", {"order": "asc", "limit": "200"}) or {}).get("data") or []
    asst = next((m["id"] for m in msgs if m.get("type") == "assistant"), None)
    if asst:
        p.post("LEADMSG-D4: an assistant message's id.", delivery="queue", mid=asst, track=False,
               label="X-6-assistant-id")
    idle = next((m["id"] for m in msgs if m.get("type") == "idle"), None)
    if idle:
        p.post("LEADMSG-D5: an idle message's id.", delivery="queue", mid=idle, track=False, label="X-7-idle-id")
    p.post("LEADMSG-D6: a session that does not exist.", delivery="queue", track=False,
           session="ses_" + "0" * 26, label="X-8-no-session")
    p.post("LEADMSG-D7: a malformed id.", delivery="queue", mid="nope_123", track=False, label="X-9-bad-id")
    p.sleep(4)
    p.state("end")


def d_render(p: Probe) -> None:
    start = p.wait_file("step-a.start", 60)
    p.mark("step-start", t=start)
    p.sleep(2)
    rec = p.post(framed("LEADMSG-F1"), delivery="queue",
                 metadata={"aew_message": "MSG-PROBE-0001", "aew_thread": "I-PROBE-0001", "probe": "PROBE-META-1"},
                 label="F1")
    p.wait_turn(timeout=90)
    c, sid = p.adapter.client, p.adapter.session
    try:
        p.result["stored_message"] = c.get(f"/api/session/{sid}/message/{rec['id']}")
    except OpenCodeError as exc:
        p.result["stored_message"] = {"status": exc.status, "body": exc.body}
    for path in (f"/api/session/{sid}/context", f"/api/session/{sid}"):
        try:
            p.result.setdefault("context_reads", {})[path] = c.get(path)
        except OpenCodeError as exc:
            p.result.setdefault("context_reads", {})[path] = {"status": exc.status, "body": exc.body}
    spec = c.get("/openapi.json", timeout=60)
    p.result["live_paths"] = sorted((spec or {}).get("paths", {}).keys())


def d_kill(p: Probe) -> None:
    ad = p.adapter
    start = p.wait_file("step-a.start", 60)
    p.mark("step-start", t=start)
    p.sleep(2)
    a = p.post("LEADMSG-K1: queued, then the server dies.", delivery="queue", label="K1")
    p.sleep(2)
    p.state("before-kill")
    assert ad.server is not None
    t_kill = time.time()
    ad.server.proc.kill()  # this run's own server, by its handle: a server crash
    ad.server.proc.wait(timeout=10)
    p.mark("server-killed", returncode=ad.server.proc.returncode)
    turn = p.wait_turn(("ended",), timeout=30)
    p.result["kill"] = {"t_kill": t_kill, "detected_s": round(time.time() - t_kill, 3), "turn": turn,
                        "inspect": ad.inspect()}
    try:
        ad.client.get(f"/api/session/{ad.session}/inbox")
        p.result["kill"]["rest_after"] = "answered"
    except OpenCodeUnavailable as exc:
        p.result["kill"]["rest_after"] = f"OpenCodeUnavailable: {exc}"[:200]
    except OpenCodeError as exc:
        p.result["kill"]["rest_after"] = {"status": exc.status, "body": exc.body}
    # A new server on the same private state (AEW never does this: a relaunch is a new run with new state).
    config = json.loads((p.run_dir / "harness" / "opencode-config.json").read_text(encoding="utf-8"))
    state = p.run_dir / "harness"
    env = server_env(dict(os.environ), state, provider_env=[], config=config, password=secrets.token_urlsafe(32))
    env["NO_PROXY"] = "127.0.0.1,localhost"
    # A fresh process tree (same containment) for the new servers: on POSIX the killed server led the run's
    # process group, which takes no new members.
    tree2 = ProcessTree(p.layout) if p.layout is not None else ProcessTree()
    p.extra_trees.append(tree2)
    s2 = Server.start(tree2.spawn, oc_adapter.binary_command(), env=env, cwd=ad.directory,
                      log_path=state / "server2.log")
    p.extra_servers.append(s2)
    c2 = s2.client
    p.mark("server-2-started")
    same: dict[str, Any] = {}
    try:
        same["session"] = bool((c2.get(f"/api/session/{ad.session}") or {}).get("data"))
    except OpenCodeError as exc:
        same["session"] = {"status": exc.status, "body": exc.body}
    for _ in range(3):
        try:
            same.setdefault("inbox", []).append(
                [i.get("id") for i in (c2.get(f"/api/session/{ad.session}/inbox") or {}).get("data") or []])
            same.setdefault("active", []).append(ad.session in ((c2.get("/api/session/active") or {}).get("data")
                                                                 or {}))
        except (OpenCodeError, OpenCodeUnavailable) as exc:
            same.setdefault("errors", []).append(str(exc)[:200])
        time.sleep(5)
    try:
        c2.get(f"/api/session/{ad.session}/message/{a['id']}")
        same["k1_delivered"] = True
    except OpenCodeError as exc:
        same["k1_delivered"] = {"status": exc.status, "body": exc.body}
    try:
        c2.get(f"/api/session/{ad.session}/message/msg_{'0' * 24}")
    except OpenCodeError as exc:
        same["unknown_message_404"] = {"status": exc.status, "body": exc.body}
    msgs = (c2.get(f"/api/session/{ad.session}/message", {"order": "asc", "limit": "200"}) or {}).get("data") or []
    same["messages"] = [{"type": m.get("type"), "id": m.get("id"), "text": (m.get("text") or "")[:120],
                         "outcome": m.get("outcome")} for m in msgs]
    p.result["same_state_restart"] = same
    s2.close(wait_s=10)
    p.mark("server-2-closed", returncode=s2.proc.poll())
    # A new server on fresh state: the session is gone (the 404 path).
    fresh = p.run_dir / "harness" / "fresh"  # inside the layout's writable harness directory
    fresh.mkdir()
    env3 = server_env(dict(os.environ), fresh, provider_env=[], config=config, password=secrets.token_urlsafe(32))
    env3["NO_PROXY"] = "127.0.0.1,localhost"
    tree3 = ProcessTree(p.layout) if p.layout is not None else ProcessTree()
    p.extra_trees.append(tree3)
    s3 = Server.start(tree3.spawn, oc_adapter.binary_command(), env=env3, cwd=ad.directory,
                      log_path=fresh / "server3.log")
    p.extra_servers.append(s3)
    gone: dict[str, Any] = {}
    for path in (f"/api/session/{ad.session}", f"/api/session/{ad.session}/message/{a['id']}",
                 f"/api/session/{ad.session}/inbox"):
        try:
            gone[path] = s3.client.get(path)
        except OpenCodeError as exc:
            gone[path] = {"status": exc.status, "body": exc.body}
    try:
        s3.client.post(f"/api/session/{ad.session}/prompt", {"id": a["id"], "text": "x", "delivery": "queue"})
        gone["prompt"] = "accepted"
    except OpenCodeError as exc:
        gone["prompt"] = {"status": exc.status, "body": exc.body}
    p.result["fresh_state"] = gone
    s3.close(wait_s=10)


def d_steer_after_short(p: Probe) -> None:
    """Two shell calls in one step (30 s and 4 s, run in parallel); steer once the short one has ended."""
    p.mark("step-a-start", t=p.wait_file("step-a.start", 60))
    p.mark("step-b-end", t=p.wait_file("step-b.end", 60))
    p.sleep(1)
    p.post("LEADMSG-P1: steer while the long parallel call still runs.", delivery="steer", label="P1")
    p.wait_turn(timeout=120)


def heartbeat_cmd(seconds: int) -> str:
    """A blocking command that writes a heartbeat (epoch ms) every 5 s: it shows whether a timed-out command is
    killed or keeps running."""
    if WINDOWS:
        ms = "([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
        return (f"Set-Content -Path {{MARK}}/step-a.start -Value {ms}; 1..{seconds // 5} | ForEach-Object "
                f"{{ Start-Sleep -Seconds 5; Set-Content -Path {{MARK}}/heartbeat.txt -Value {ms} }}; 'done'")
    return (f"date +%s%3N > {{MARK}}/step-a.start; for i in $(seq {seconds // 5}); do sleep 5; "
            f"date +%s%3N > {{MARK}}/heartbeat.txt; done; echo done")


def d_heartbeat(p: Probe) -> None:
    p.mark("step-start", t=p.wait_file("step-a.start", 60))
    p.wait_turn(timeout=400)
    seen = []
    for _ in range(4):  # after the tool returned: does the command still beat?
        seen.append(p.wait_file("heartbeat.txt", 1))
        p.sleep(5)
    p.result["heartbeat_after_turn"] = [round(t - p.t0, 3) if t else None for t in seen]


def d_shell_timeout(p: Probe) -> None:
    start = p.wait_file("step-a.start", 60)
    p.mark("step-start", t=start)
    p.wait_turn(timeout=1500)


S = step_cmd
CASES: dict[str, dict[str, Any]] = {
    # P1: mid-turn queue, during a 30 s shell step and during a 15 s model call.
    "p1-queue-shell": {"script": [{"shell": S("a", 30)}, {"text": "Step 2 done."}], "driver": d_queue_shell("queue")},
    "p1-queue-model": {"script": [{"read": "big_0.txt", "delay": 15}, {"text": "Step 2 done."}],
                       "driver": d_queue_model("queue")},
    # P1 with a longer turn: the shell step is followed by two more tool steps before the final answer.
    "p1-queue-shell-multi": {"script": [{"shell": S("a", 30)}, {"read": "big_1.txt"}, {"read": "big_2.txt"},
                                        {"text": "Step 4 done."}], "driver": d_queue_shell("queue")},
    "p1-queue-model-multi": {"script": [{"read": "big_0.txt", "delay": 15}, {"read": "big_1.txt"},
                                        {"read": "big_2.txt"}, {"text": "Step 4 done."}],
                             "driver": d_queue_model("queue")},
    # P2: mid-turn steer, the same two situations.
    "p2-steer-shell-multi": {"script": [{"shell": S("a", 30)}, {"read": "big_1.txt"}, {"read": "big_2.txt"},
                                        {"text": "Step 4 done."}], "driver": d_queue_shell("steer")},
    "p2-steer-model-multi": {"script": [{"read": "big_0.txt", "delay": 15}, {"read": "big_1.txt"},
                                        {"read": "big_2.txt"}, {"text": "Step 4 done."}],
                             "driver": d_queue_model("steer")},
    "p2-steer-shell": {"script": [{"shell": S("a", 30)}, {"text": "Step 2 done."}], "driver": d_queue_shell("steer")},
    "p2-steer-model": {"script": [{"read": "big_0.txt", "delay": 15}, {"text": "Step 2 done."}],
                       "driver": d_queue_model("steer")},
    # P3: idle sessions. (a) held after a Lead interrupt; (b) the closing window; (c) resume: false.
    "p3a-held": {"script": [{"shell": S("a", 30)}, {"text": "Step 2 done."}], "driver": d_held},
    "p3b-closing-inflight": {"script": [{"text": "Final answer.", "delay": 12}], "driver": d_closing_inflight},
    "p3b-closing-after": {"script": [{"text": "Final answer."}], "driver": d_closing_after},
    "p3c-idle-noresume": {"script": [{"text": "First turn done."}], "driver": d_idle_noresume},
    "p3c-busy-noresume": {"script": [{"shell": S("a", 20)}, {"text": "Step 2 done."}], "driver": d_busy_noresume},
    # P4: ordering. Five rapid queue posts; a mixed steer/queue sequence.
    "p4-five-queue": {"script": [{"shell": S("a", 15)}, {"text": "Step 2 done."}],
                      "driver": d_ordering([(f"O{i}", "queue") for i in range(1, 6)])},
    "p4-mixed": {"script": [{"shell": S("a", 15)}, {"text": "Step 2 done."}],
                 "driver": d_ordering([("M1q", "queue"), ("M2s", "steer"), ("M3q", "queue"), ("M4s", "steer"),
                                       ("M5q", "queue")])},
    "p2-steer-parallel": {"script": [{"multi": [{"shell": S("a", 30)}, {"shell": S("b", 4)}]},
                                     {"read": "big_1.txt"}, {"text": "Step 3 done."}],
                          "driver": d_steer_after_short},
    # P2 and D-22: does a delivered Lead input reset OpenCode's step limit (here 4 steps)? Steer at step 2.
    "p2-steps-steer": {"script": [{"shell": S("a", 8)}] + [{"read": f"big_{i % 4}.txt"} for i in range(9)],
                       "steps": 4, "driver": d_queue_shell("steer")},
    "p2-steps-none": {"script": [{"shell": S("a", 8)}] + [{"read": f"big_{i % 4}.txt"} for i in range(9)],
                      "steps": 4, "driver": d_shell_timeout},
    # The same P3 and P4 questions with steer, the delivery P1/P2 select.
    "p3a-held-steer": {"script": [{"shell": S("a", 30)}, {"text": "Step 2 done."}],
                       "driver": lambda p: d_held(p, "steer")},
    "p3b-closing-inflight-steer": {"script": [{"text": "Final answer.", "delay": 12}],
                                   "driver": lambda p: d_closing_inflight(p, "steer")},
    "p3c-idle-noresume-steer": {"script": [{"text": "First turn done."}],
                                "driver": lambda p: d_idle_noresume(p, "steer")},
    "p4-five-steer": {"script": [{"shell": S("a", 15)}, {"read": "big_1.txt"}, {"text": "Step 3 done."}],
                      "driver": d_ordering([(f"S{i}", "steer") for i in range(1, 6)])},
    # P5: the same id twice, and 409s for other causes.
    "p5-duplicate": {"script": [{"shell": S("a", 20)}, {"text": "Step 2 done."}], "driver": d_duplicate},
    # P6: what the worker sees.
    "p6-render": {"script": [{"shell": S("a", 10)}, {"text": "Step 2 done."}], "driver": d_render},
    # P7: session loss with an item queued.
    "p7-kill": {"script": [{"shell": S("a", 60)}, {"text": "Step 2 done."}], "driver": d_kill},
    # P9: the shell tool's timeout. Blocking calls of 120, 300 and 600 s with the default timeout, and with an
    # explicit timeout (300 s under 360000 ms; 600 s with the timeout disabled, 0).
    "p9-120": {"script": [{"shell": S("a", 120)}, {"text": "Done."}], "driver": d_shell_timeout},
    "p9-300": {"script": [{"shell": S("a", 300)}, {"text": "Done."}], "driver": d_shell_timeout},
    "p9-600": {"script": [{"shell": S("a", 600)}, {"text": "Done."}], "driver": d_shell_timeout},
    "p9-300-t360": {"script": [{"shell": S("a", 300), "timeout": 360000}, {"text": "Done."}],
                    "driver": d_shell_timeout},
    "p9-killcheck": {"script": [{"shell": heartbeat_cmd(300)}, {"text": "Done."}], "driver": d_heartbeat},
    "p9-600-t0": {"script": [{"shell": S("a", 600), "timeout": 0}, {"text": "Done."}], "driver": d_shell_timeout},
}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--list"]:
        print("\n".join(CASES))
        return 0
    if len(argv) != 3 or argv[1] not in CASES:
        print(__doc__.split("\n\n", 2)[1], file=sys.stderr)
        return 2
    out, case, rep = Path(argv[0]), argv[1], argv[2]
    res = Probe(out, case, rep).run()
    print(json.dumps({k: res.get(k) for k in ("case", "rep", "version", "error", "driver_error", "inspect",
                                                "lease_close", "elapsed_s")}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
