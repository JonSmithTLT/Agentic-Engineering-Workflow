"""Capture the no-run seeded off surface for a main-source golden, never runtime qualification.

Only volatile paths, times, token IDs, git/content digests and durations are normalized; field names, instructions,
ordering and JSON/text bodies are pinned. The no-run wait is an actual refusal, not a synthetic ended-run owner fact.
Existing progress/wait integration tests cover real ended runs; the golden does not claim arbitrary project coverage.
An optional source root supports generation against clean merged main, not a CI dependency.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main():
    root, work = Path(sys.argv[1]), sys.argv[2]
    src = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parents[2] / "src"
    sys.path.insert(0, str(src))
    from aew.engine.api import Engine
    from aew.errors import AEWError
    from aew.surface import readable, run
    from aew.surface.context import SurfaceContext

    engine = Engine.discover(root)

    def wait():
        try:
            return engine.harness_wait("R-INV-0001-1", timeout=0, triggers=True)
        except AEWError as exc:
            return {"error": exc.to_dict()}

    status, resume = engine.status(work), engine.resume()
    values = {"status": status, "status_text": engine.render_status(status), "resume": resume,
              "resume_text": engine.render_resume(resume), "harness_status": engine.harness_status(),
              "harness_wait": wait(), "work_show": engine.work_show(work)}
    for name, args in (("status", {"work_id": work}), ("resume", {}), ("harness_status", {}),
                       ("work_show", {"work_id": work}), ("harness_wait", {"runs": ["R-INV-0001-1"]})):
        result = run.run_tool(engine, SurfaceContext.outside_session(), name, args)
        values["typed_" + name] = {"json": result, "text": readable.render(result)}
    # Cross-host separators and locations are not evidence of an off-surface behavior change.
    places = [str(root), str(root.parent), str(engine.work_show(work).get("workspace") or "")]

    def clean(value):
        if isinstance(value, dict):
            return {k: "<duration>" if k.endswith("_ms") else clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        if not isinstance(value, str):
            return value
        value = value.replace("\\\\", "/").replace("\\", "/")
        for place in sorted(filter(None, places), key=len, reverse=True):
            value = value.replace(place.replace("\\", "/"), "<project>")
        value = re.sub(r"\b[0-9a-f]{40,64}\b", "<digest>", value)
        value = re.sub(r"\btk_[0-9a-f]{16}\b", "<token-id>", value)
        return re.sub(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)", "<time>", value)

    print(json.dumps(clean(values), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
