"""P5's response bodies as an id-only table. Usage: p5_table.py DATA_DIR[=LABEL] ...

The raw ``posts.jsonl`` of the ``p5-duplicate-*`` runs keeps every POST's full body, which is never committed. This
prints what the evidence needs from them, with ids only: for each post, the delivery sent, the status, and either the
item OpenCode returned (its id, whether its id, ``time.created``, text and delivery equal the first post's) or the
error's ``_tag`` with the id or session it names. No message text appears.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(p: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def yes(flag: bool) -> str:
    return "yes" if flag else "no"


def rows(run: Path) -> list[list[str]]:
    posts = load(run / "posts.jsonl")
    first = (posts[0].get("response") or {}).get("data") or {}
    out = []
    for p in posts:
        sent = p["request"].get("delivery") or "-"
        resp = p.get("response") or {}
        if p["status"] == 200:
            item = resp.get("data") or {}
            answer = (f"item `{item.get('id')}` (same id: {yes(item.get('id') == first.get('id'))}; "
                      f"same `time.created`: {yes(item.get('time') == first.get('time'))}; "
                      f"same text: {yes(item.get('payload') == first.get('payload'))}; "
                      f"delivery `{item.get('delivery')}`)")
        else:
            named = resp.get("resource") or resp.get("messageID") or resp.get("sessionID")
            answer = f"`{resp.get('_tag')}`" + (f", names `{named}`" if named else "")
        out.append([p["label"], sent, str(p["status"]), answer])
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    print("| host | run | post | delivery sent | status | answer (ids only) |")
    print("|---|---|---|---|---|---|")
    for arg in sys.argv[1:]:
        path, _, label = arg.partition("=")
        root = Path(path)
        for run in sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("p5-duplicate-")):
            for r in rows(run):
                print(f"| {label or root.name} | {run.name} | " + " | ".join(r) + " |")


if __name__ == "__main__":
    main()
