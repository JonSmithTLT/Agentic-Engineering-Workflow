"""The report's tables, from both hosts' run directories. Usage: table.py DATA_DIR[=LABEL] ...

Per run: when each Lead input was admitted relative to the step it was posted during (P1, P2), the delivery order
(P4), statuses (P5), and the shell tool's fate (P9). Times are seconds; "after step end" is the delivered event's
receipt minus the end of the step in flight at the post (the shell step's end marker, or the delayed model call's
answer).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# summarize is a sibling module: a script's own directory is first on sys.path.
from summarize import load, run_metrics


def step_end(d: Path, m: dict) -> float | None:
    if "step-a.end" in m["files"]:
        return m["files"]["step-a.end"]
    res = json.loads((d / "result.json").read_text(encoding="utf-8"))
    for r in load(d / "model.jsonl"):
        if r["ev"] == "resp" and r.get("main_ordinal") == 1 and r.get("delay"):
            return r["t"] - res["t0"]
    return None


def main() -> None:
    hosts = []
    for arg in sys.argv[1:]:
        path, _, label = arg.partition("=")
        hosts.append((Path(path), label or Path(path).name))
    rows = []
    for root, label in hosts:
        for d in sorted(p for p in root.iterdir() if p.is_dir() and (p / "result.json").exists()):
            m = run_metrics(d)
            end = step_end(d, m)
            for p in m["posts"]:
                if not (d.name.startswith("p1") or d.name.startswith("p2")):
                    continue
                after = (round(p["s_delivered_ev"] - end, 3) if (end is not None and p["s_delivered_ev"]) else None)
                rows.append((label, d.name, p["label"], p["delivery"], p["s_post"], end and round(end, 3),
                             p["s_delivered_ev"], p["s_rest_200"], after, p["requests_between"],
                             m["shell"]["tool_event"] if m.get("shell") else "-",
                             m["n_model_requests"]))
    print("| host | run | input | delivery | posted | step end | delivered (event) | REST 200 | after step end |"
          " model requests in between | running tool | requests |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    print()
    print("| host | run | delivered order | statuses | turn | exit |")
    print("|---|---|---|---|---|---|")
    for root, label in hosts:
        for d in sorted(p for p in root.iterdir() if p.is_dir() and (p / "result.json").exists()):
            if d.name.startswith(("p1", "p2", "p9")):
                continue
            m = run_metrics(d)
            st = ", ".join(f"{p['label']}={p['status']}" for p in m["posts"])
            print(f"| {label} | {d.name} | {' > '.join(m['delivered_order'][1:])} | {st} | "
                  f"{(m['inspect'] or {}).get('turn')} | {(m['inspect'] or {}).get('exit_code')} |")
    print()
    print("| host | run | shell started | tool result at | duration | end marker | result |")
    print("|---|---|---|---|---|---|---|")
    for root, label in hosts:
        for d in sorted(p for p in root.iterdir() if p.is_dir() and (p / "result.json").exists()):
            if not d.name.startswith("p9"):
                continue
            m = run_metrics(d)
            sh = m.get("shell") or {}
            tail = (sh.get("result_tail") or "").replace("\r", "").replace("\n", " ")[-70:]
            res = json.loads((d / "result.json").read_text(encoding="utf-8"))
            hb = res.get("heartbeat_after_turn")
            print(f"| {label} | {d.name} | {sh.get('start_s')} | {sh.get('tool_result_s')} | "
                  f"{sh.get('tool_duration_s')} | {'written' if sh.get('end_file_s') else 'absent'} | {tail}"
                  f"{' (last heartbeat ' + str(hb[-1]) + ' s)' if hb else ''} |")


if __name__ == "__main__":
    main()
