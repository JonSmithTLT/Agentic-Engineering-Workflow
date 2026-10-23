"""Record real HTTP responses of a running STG-02 slice producer (docs/stg02/BACKEND-REPORT.md, "Recorded responses").

    python tools/stg02/record_responses.py --base http://127.0.0.1:4261 --config docs/stg02/driver-config.json \
        --real-run <AEW invocation id> --real-work <AEW work id> --out docs/stg02/recordings

The server must run with ``--fixture-recipient --test-routes --project <AEW project>`` and with ``--tokens`` naming
``token-other-synthetic`` (a synthetic token, for the second recipient). Each recording is one exchange: the request
(method, path, headers, body) and the response (status, the wire headers, body) exactly as received. Keys are suffixed
per run, so recording twice never replays an earlier run's keys.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

D01 = {"X-AEW-Wire-Version": "0.3.4"}
O01 = {"X-AEW-O01-Wire": "o01-command-0.2-review-candidate"}
KEEP = ("content-type", "cache-control", "x-aew-wire-version", "x-aew-o01-wire")


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


class Recorder:
    def __init__(self, base: str, out: Path) -> None:
        if not base.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise SystemExit("--base must be the local slice server, http://127.0.0.1:<port>")
        self.base, self.out = base.rstrip("/"), out
        out.mkdir(parents=True, exist_ok=True)

    def call(self, name: str | None, method: str, path: str, headers: dict[str, str] | None = None,
             body: Any = None) -> tuple[int, Any]:
        h = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)  # noqa: S310 (loopback http)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (loopback http only, checked in __init__)
                status, hdrs, raw = r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            status, hdrs, raw = e.code, e.headers, e.read()
        parsed = json.loads(raw) if raw else None
        if name:
            rec = {"request": {"method": method, "path": path, "headers": h, "body": body},
                   "response": {"status": status, "headers": {k: hdrs.get(k) for k in KEEP if hdrs.get(k)},
                                "body": parsed}}
            (self.out / f"{name}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n",
                                                   encoding="utf-8", newline="\n")
        return status, parsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--real-run", required=True)
    ap.add_argument("--real-work", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    cfg = json.loads(a.config.read_text(encoding="utf-8"))
    tag = datetime.now(UTC).strftime("rec%Y%m%dT%H%M%S")
    r = Recorder(a.base, a.out)

    def cset(src: dict[str, Any], name: str) -> dict[str, Any]:
        c = copy.deepcopy(src)
        c["client_request_key"] += f".{tag}.{name}"
        c["request_set_ref"] += f".{tag}.{name}"
        return c

    cont, run = b64("fixture:ticket-continue"), b64("fixture:run-continue-1")
    # 1. waiting
    r.call("waiting-200", "GET", "/v1/read/waiting?limit=20", D01)
    _, first = r.call("waiting-200-page1-limit2", "GET", "/v1/read/waiting?limit=2", D01)
    r.call("waiting-200-page2-limit2", "GET", f"/v1/read/waiting?limit=2&cursor={first['page']['next_cursor']}", D01)
    cursor = first["page"]["next_cursor"]
    r.call("waiting-409-cursor-other-recipient", "GET", f"/v1/read/waiting?limit=2&cursor={cursor}",
           {**D01, "Authorization": "Bearer token-other-synthetic"})
    r.call("waiting-400-no-version", "GET", "/v1/read/waiting")
    r.call("waiting-400-version-0.3.3", "GET", "/v1/read/waiting", {"X-AEW-Wire-Version": "0.3.3"})
    r.call("waiting-401-unknown-bearer", "GET", "/v1/read/waiting", {**D01, "Authorization": "Bearer not-issued"})
    # 2. runs
    r.call("run-200-fixture-unknown-remote-effect", "GET", f"/v1/read/runs/{run}", D01)
    r.call("run-200-real-aew-invocation", "GET", f"/v1/read/runs/{b64(a.real_run)}", D01)
    r.call("run-404-unknown", "GET", f"/v1/read/runs/{b64('fixture:run-unknown')}", D01)
    r.call("run-404-hidden-member", "GET", f"/v1/read/runs/{b64('fixture:run-hidden-1')}", D01)
    r.call("run-400-noncanonical-id", "GET", f"/v1/read/runs/{run}=", D01)
    r.call(None, "POST", "/_test/engine-outage", body={"unavailable": True})
    try:
        r.call("run-503-real-source-unavailable", "GET", f"/v1/read/runs/{b64(a.real_run)}", D01)
        r.call("waiting-200-partial-real-source-unavailable", "GET", "/v1/read/waiting", D01)
        r.call("continuation-503-real-source-unavailable", "GET",
               f"/v1/read/continuation-state/{b64(a.real_work)}", D01)
    finally:
        r.call(None, "POST", "/_test/engine-outage", body={"unavailable": False})
    # 3. continuation state
    r.call("continuation-200-fixture", "GET", f"/v1/read/continuation-state/{cont}", D01)
    r.call("continuation-200-real-aew-work", "GET", f"/v1/read/continuation-state/{b64(a.real_work)}", D01)
    r.call("continuation-404-unknown", "GET", f"/v1/read/continuation-state/{b64('fixture:ticket-unknown')}", D01)
    r.call("continuation-401-malformed-authorization", "GET", f"/v1/read/continuation-state/{cont}",
           {**D01, "Authorization": "Basic abc"})
    # 4. command sets
    ok = cset(cfg["command"]["continue_eligible_work"], "p07")
    _, receipt = r.call("command-202-p07-admitted", "POST", "/o01/v0/command-sets", O01, ok)
    r.call("command-202-identical-retry-same-receipt", "POST", "/o01/v0/command-sets", O01, ok)
    r.call("command-409-request-key-conflict", "POST", "/o01/v0/command-sets", O01,
           {**ok, "request_set_ref": ok["request_set_ref"] + "-changed"})
    r.call("command-400-no-o01-header", "POST", "/o01/v0/command-sets", None, cset(ok, "hdr"))
    r.call("command-401-recipient-not-authenticated", "POST", "/o01/v0/command-sets", O01,
           {**cset(ok, "rcpt"), "recipient_ref": "fixture:recipient-other"})
    r.call("command-202-n22-c17n02-intent-not-granted", "POST", "/o01/v0/command-sets", O01,
           cset(cfg["c17_cases"]["C17-N02"]["request"], "n22"))
    r.call("command-202-c17n01-delegation-expired", "POST", "/o01/v0/command-sets", O01,
           cset(cfg["c17_cases"]["C17-N01"]["request"], "n01"))
    held = cset(cfg["command"]["continue_eligible_work"], "n21")
    held["intents"] = [json.loads(json.dumps(cfg["command"]["continue_eligible_work"]["intents"][0]))]
    held["intents"][0].update(intent_ref="fixture:intent-continue-held",
                              delegated_grant_proof_ref="fixture:delegation-held-current")
    held["intents"][0]["target"].update(work_ref="fixture:ticket-held", grant_ref="fixture:grant-ticket-held",
                                        eligible_basis_ref="fixture:basis-not-eligible-held")
    held["intents"][0]["predecessor"]["basis_ref"] = "fixture:basis-not-eligible-held"
    r.call("command-202-n21-heb-work-not-eligible", "POST", "/o01/v0/command-sets", O01, held)
    r.call("command-202-protected-attach-without-g3", "POST", "/o01/v0/command-sets", O01,
           cset(cfg["command"]["protected_without_g3"], "attach"))
    rcpt = ok["recipient_ref"]
    r.call(None, "POST", "/_test/read-entitlement", body={"recipient_ref": rcpt, "entitled": False})
    try:
        r.call("command-404-c17n03-retry-after-entitlement-withdrawn", "POST", "/o01/v0/command-sets", O01, ok)
    finally:
        r.call(None, "POST", "/_test/read-entitlement", body={"recipient_ref": rcpt, "entitled": True})
    # 5. outcome after reload
    op = receipt["results"][0]["operation_ref"]
    r.call("owner-get-200-admitted", "GET", f"/o01/v0/owner-operations/HEB/{op}", O01)
    r.call("owner-get-404-other-recipient", "GET", f"/o01/v0/owner-operations/HEB/{op}",
           {**O01, "Authorization": "Bearer token-other-synthetic"})
    r.call("owner-get-404-unknown", "GET", "/o01/v0/owner-operations/HEB/op:unknown", O01)
    r.call("owner-operations-200", "GET", "/v1/read/owner-operations?scope_ref=fixture:scope-slice", D01)
    r.call("owner-operations-400-unknown-owner", "GET", "/v1/read/owner-operations?owner=NOBODY", D01)
    r.call("owner-operations-404-undisclosed-scope", "GET", "/v1/read/owner-operations?scope_ref=fixture:scope-other",
           D01)
    r.call("owner-operations-409-forged-cursor", "GET", "/v1/read/owner-operations?cursor=c1.0.forged", D01)
    print(f"recorded {len(list(a.out.glob('*.json')))} exchanges in {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
