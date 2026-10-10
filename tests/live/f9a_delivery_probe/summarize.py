"""Per-run metrics for the MS0 report. Usage: summarize.py DATA_DIR [--json]

For each run directory (``<case>-<rep>``) prints the facts the plan's questions ask for: when each Lead input was
posted, enqueued and delivered (event and REST), the step boundary it was admitted at, what the model saw, the
running tool's fate, statuses and bodies, and the shell timeout results. ``--json`` writes the per-host summary
committed as evidence (``summary-<host>.json``). It copies only times, statuses, ids, OpenCode's answers and the
probe's own labels, never a path: ``tests/unit/test_f9a_probe_evidence.py`` checks the committed copies.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


def load(p: Path) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def marker_of(text: str) -> str | None:
    m = re.search(r"LEADMSG-[A-Za-z0-9_]+", text or "")
    return m.group(0) if m else None


def run_metrics(d: Path) -> dict[str, Any]:
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    t0 = res["t0"]
    posts = load(d / "posts.jsonl")
    model = load(d / "model.jsonl")
    events = load(d / "events.jsonl")
    deliveries = {(r["id"], r.get("label")): r for r in load(d / "deliveries.jsonl")}
    reqs = [r for r in model if r["ev"] == "req" and r["kind"] == "main"]
    resps = {r["n"]: r for r in model if r["ev"] == "resp"}
    files: dict[str, float] = {}
    for f in [*(d / "workspace").glob("step-*"), *(d / "run" / "scratch").glob("step-*")]:
        try:
            files[f.name] = int(f.read_text(encoding="utf-8-sig").strip()) / 1000 - t0
        except ValueError:
            pass
    delivered_ev = {}
    enqueued_ev = {}
    order_delivered: list[str] = []
    for e in events:
        data = e.get("data") or {}
        if e.get("type") == "session.inbox.delivered":
            delivered_ev.setdefault(data.get("inboxID"), e["s"])
            order_delivered.append(data.get("inboxID"))
        if e.get("type") == "session.inbox.enqueued":
            enqueued_ev.setdefault(data.get("inboxID"), e["s"])
    def tail(data: dict[str, Any]) -> str:
        return "".join(c.get("text", "") for c in data.get("content") or [] if isinstance(c, dict))[-160:]

    tools = [(e["s"], e.get("type"), (e.get("data") or {}).get("id"), (e.get("data") or {}).get("error"),
              tail(e.get("data") or {}))
             for e in events if e.get("type") in ("session.tool.success", "session.tool.failed")]
    out: dict[str, Any] = {"run": d.name, "version": res.get("version"), "error": res.get("error"),
                           "driver_error": res.get("driver_error"), "inspect": res.get("inspect"),
                           "lease_close": res.get("lease_close"), "files": {k: round(v, 3) for k, v in files.items()},
                           "n_model_requests": len(reqs), "tools": tools}
    per: list[dict[str, Any]] = []
    for p in posts:
        mid = p["id"]
        mk = marker_of(p["request"].get("text", ""))
        first_seen = next((r for r in reqs if mk and mk in r["markers"]), None)
        # the main request in flight (or the last one answered) when the post was made
        before = [r for r in reqs if r["t"] <= p["t_send"]]
        in_step = before[-1]["main_ordinal"] if before else None
        dv = deliveries.get((mid, p["label"])) or {}
        per.append({
            "label": p["label"], "delivery": p["request"].get("delivery"), "resume": p["request"].get("resume"),
            "status": p["status"], "s_post": round(p["t_send"] - t0, 3),
            "s_enqueued_ev": enqueued_ev.get(mid), "s_delivered_ev": delivered_ev.get(mid),
            "s_rest_200": round(dv["t_200"] - t0, 3) if dv.get("t_200") else None, "rest_404s": dv.get("n404"),
            "posted_during_request": in_step,
            "first_seen_by_request": first_seen["main_ordinal"] if first_seen else None,
            "s_first_seen": round(first_seen["t"] - t0, 3) if first_seen else None,
            "requests_between": (first_seen["main_ordinal"] - in_step - 1) if (first_seen and in_step) else None,
            "response": p.get("response") if p["status"] != 200 else None,
        })
    out["posts"] = per
    out["delivered_order"] = [next((p["label"] for p in posts if p["id"] == i), i[-6:] if i else i)
                              for i in order_delivered]
    last = reqs[-1] if reqs else None
    out["markers_in_last_request"] = last["markers"] if last else None
    out["metadata_visible_any"] = any(any(r["metadata_visible"].values()) for r in reqs)
    out["model_client_gone"] = [r for r in resps.values() if str(r.get("outcome", "")).startswith("client_gone")]
    for k in ("kill", "same_state_restart", "fresh_state", "stored_message"):
        if k in res:
            out[k] = res[k]
    # the shell tool's fate and duration (P9)
    if "step-a.start" in files:
        shell = next((t for t in tools if t[2] and t[2].startswith("call_ms0_1")), None)
        out["shell"] = {"start_s": round(files["step-a.start"], 3), "end_file_s": files.get("step-a.end"),
                        "tool_result_s": shell[0] if shell else None,
                        "tool_duration_s": round(shell[0] - files["step-a.start"], 3) if shell else None,
                        "tool_event": shell[1] if shell else None, "tool_error": shell[3] if shell else None,
                        "result_tail": shell[4] if shell else None}
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    root = Path(args[0])
    runs = sorted(p for p in root.iterdir() if p.is_dir() and (p / "result.json").exists())
    metrics = [run_metrics(d) for d in runs]
    if "--json" in sys.argv:
        print(json.dumps(metrics, indent=1, default=str))
        return
    for m in metrics:
        print(f"== {m['run']}  version={m['version']} err={m['error'] or m['driver_error']} "
              f"turn={(m['inspect'] or {}).get('turn')} exit={(m['inspect'] or {}).get('exit_code')} "
              f"requests={m['n_model_requests']} lease={m['lease_close']}")
        print(f"   files={m['files']}")
        for p in m["posts"]:
            print("   POST", json.dumps({k: v for k, v in p.items() if v is not None}, default=str)[:420])
        print(f"   delivered_order={m['delivered_order']} last_request_markers={m['markers_in_last_request']} "
              f"metadata_visible={m['metadata_visible_any']} model_aborts={len(m['model_client_gone'])}")
        for t in m["tools"]:
            print(f"   TOOL {t[0]:.3f} {t[1]} {t[2]} err={t[3]} tail={t[4][-90:]!r}")
        if m.get("shell"):
            print("   SHELL", json.dumps(m["shell"])[:400])
        for k in ("kill", "same_state_restart", "fresh_state"):
            if k in m:
                print(f"   {k.upper()}", json.dumps(m[k], default=str)[:700])


if __name__ == "__main__":
    main()
