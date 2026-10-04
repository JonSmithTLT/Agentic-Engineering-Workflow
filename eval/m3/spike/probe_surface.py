"""Spike probe 1: private server, lease, served OpenAPI, models/variants, skills, agents (no model calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from v2lib import PINNED_BIN, isolated_env, start_server


def main(root: Path, out: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    ws = root / "workspace"
    ws.mkdir(exist_ok=True)
    (ws / "AGENTS.md").write_text("# spike AGENTS.md: must not load under OPENCODE_DISABLE_PROJECT_CONFIG\n")
    result: dict = {"binary": str(PINNED_BIN), "exists": PINNED_BIN.exists()}
    for variant, config in (("default", {}),
                            ("compat_disabled", {"plugins": ["-opencode.config.compatibility"]})):
        env = isolated_env(root / f"state-{variant}", config=config)
        srv = start_server(env, ws)
        r: dict = {"start_s": round(srv.started_s, 3), "url": srv.url}
        loc = {"location[directory]": str(ws)}
        r["info"] = srv.get("/api/info")
        st, spec = srv.get("/openapi.json")
        r["openapi_status"] = st
        if isinstance(spec, dict):
            (out / "openapi-2.0.18.json").write_text(json.dumps(spec, indent=1))
            r["openapi_ops"] = len([1 for p in spec.get("paths", {}).values() for _ in p])
            r["openapi_info"] = spec.get("info")
        r["unauth_info_status"] = srv.get("/api/info", auth=False)[0]
        st, models = srv.get("/api/model", params=loc)
        data = models.get("data", []) if isinstance(models, dict) else []
        r["models_status"] = st
        r["models"] = [{"provider": m.get("providerID"), "id": m.get("id"), "modelID": m.get("modelID"),
                        "variants": [v.get("id") for v in m.get("variants") or []]} for m in data][:60]
        st, skills = srv.get("/api/skill", params=loc)
        r["skills_status"] = st
        r["skills"] = [{"id": s.get("id"), "path": s.get("path")} for s in (skills or {}).get("data", [])] \
            if isinstance(skills, dict) else skills
        st, agents = srv.get("/api/agent", params=loc)
        r["agents"] = [{"id": a.get("id"), "mode": a.get("mode"), "hidden": a.get("hidden")}
                       for a in (agents or {}).get("data", [])] if isinstance(agents, dict) else agents
        r["lease_exit_s"] = srv.close_lease()
        r["exit_code"] = srv.proc.returncode
        r["stderr_tail"] = srv.stderr_lines[-5:]
        result[variant] = r
    (out / "probe_surface.json").write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items()
                                                              if kk not in {"models"}})
                      for k, v in result.items()}, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
