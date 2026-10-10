"""Print one run's merged timeline (seconds from the run's t0): posts, REST deliveries, model requests and answers,
shell step markers and the event-stream frames that matter. Usage: timeline.py DATA_DIR [--all-events]"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KEEP = {"session.inbox.enqueued", "session.inbox.delivered", "session.execution.started",
        "session.execution.succeeded", "session.execution.failed", "session.execution.interrupted",
        "session.step.started", "session.step.ended", "session.step.failed", "session.tool.called",
        "session.tool.success", "session.tool.failed", "session.synthetic", "session.inbox.cancelled",
        "session.inbox.delivery.changed", "session.shell.started", "session.shell.ended"}


def load(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    d = Path(sys.argv[1])
    allev = "--all-events" in sys.argv
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    t0 = res["t0"]
    rows: list[tuple[float, str]] = []
    for r in load(d / "posts.jsonl"):
        req = r["request"]
        rows.append((r["t_send"] - t0, f"POST {r['label']} id={r['id'][-6:]} delivery={req.get('delivery')} "
                     f"resume={req.get('resume')} -> {r['status']} ({r['t_resp'] - r['t_send']:.3f}s) "
                     f"turn_before={r['turn_before']} resp={json.dumps(r['response'])[:200]}"))
    for r in load(d / "deliveries.jsonl"):
        if r.get("t_200"):
            rows.append((r["t_200"] - t0, f"REST 200 {r['label']} id={r['id'][-6:]} (after {r['n404']} x 404)"))
        else:
            rows.append((9e9, f"REST never 200 {r['label']} id={r['id'][-6:]} n404={r['n404']} {r.get('other')}"))
    for r in load(d / "model.jsonl"):
        if r["ev"] == "req" and r["kind"] == "main":
            tr = [(x["len"], x["tail"][-80:].replace("\n", " | ")) for x in r.get("tool_results", [])]
            rows.append((r["t"] - t0, f"MODEL req #{r['main_ordinal']} markers={r['markers']} "
                         f"new={r.get('new_markers')} roles={''.join(x[0] for x in r['roles'])} "
                         f"meta={r['metadata_visible']} "
                         f"last_tool={tr[-1] if tr else None}"))
        elif r["ev"] == "resp" and r.get("main_ordinal"):
            rows.append((r["t"] - t0, f"MODEL resp #{r['main_ordinal']} {r['outcome']} {r['answer'][:90]}"))
    for f in sorted([*(d / "workspace").glob("step-*"), *(d / "run" / "scratch").glob("step-*")]):
        try:
            rows.append((int(f.read_text(encoding="utf-8-sig").strip()) / 1000 - t0, f"STEP {f.name}"))
        except ValueError:
            pass
    for r in load(d / "events.jsonl"):
        k = r.get("type")
        if allev or k in KEEP:
            data = r.get("data") or {}
            extra = {x: data[x] for x in ("inboxID", "finish", "reason", "id", "error", "delivery") if x in data}
            if k == "session.inbox.enqueued":
                item = data.get("item") or {}
                extra = {"inboxID": data.get("inboxID", "")[-6:], "delivery": item.get("delivery"),
                         "text": ((item.get("payload") or {}).get("text") or "")[:40]}
            if k == "session.tool.success" or k == "session.tool.failed":
                c = data.get("content") or []
                extra["content_tail"] = (c[-1].get("text", "")[-120:] if c and isinstance(c[-1], dict) else "")
                extra["error"] = data.get("error")
            rows.append((r["s"], f"EV {k} {json.dumps(extra, default=str)[:260]}"))
    for r in load(d / "adapter.jsonl"):
        if r.get("event") in ("opencode.prompt", "opencode.ended", "opencode.held"):
            rest = {k: v for k, v in r.items() if k not in ("t", "s", "event")}
            rows.append((r["s"], f"ADAPTER {r.get('event')} {json.dumps(rest)[:200]}"))
    for r in load(d / "marks.jsonl"):
        rest = {k: v for k, v in r.items() if k not in ("t", "s", "mark")}
        rows.append((r["s"], f"MARK {r['mark']} {json.dumps(rest, default=str)[:300]}"))
    for t, line in sorted(rows, key=lambda x: x[0]):
        print(f"{t:9.3f}  {line}")
    print("inspect:", res.get("inspect"), "| error:", res.get("error"), res.get("driver_error"))


if __name__ == "__main__":
    main()
