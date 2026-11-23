"""Exercise only the built-in, public scripted controls in fresh temporary directories."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVAL = HERE.parents[2]
sys.path[:0] = [str(EVAL), str(EVAL.parent / "src")]

from aew_eval import hidden, score_child  # noqa: E402
from aew_eval.arms import ScriptedArm  # noqa: E402

CRITERIA = ("json-field", "current-spelling", "legacy-default", "csv-exact")
# Each one-fault control mutates exactly one place in the same reference exporter.
FAULTS = {
    "json-field": (("json-field",), 'item["status"] = status',
                   'if status != "done":\n                item["status"] = status'),
    "stale-spelling": (("current-spelling",), '"pending": "queued"', '"pending": "waiting"'),
    "legacy-default": (("legacy-default",), 'row.get("phase"), "unknown"', 'row.get("phase"), "done"'),
    "csv-regression": (("csv-exact",), "csv.writer(stream)", 'csv.writer(stream, lineterminator="\\n")'),
    "batch-last-phase": (("current-spelling", "legacy-default"), 'row.get("phase")', 'rows[-1].get("phase")'),
}


def steps(control):
    """The F19 scripted edit for one named, evaluator-owned calibration control."""
    source = (HERE / "controls" / "good.py").read_text(encoding="utf-8")
    if control != "good":
        _, old, new = FAULTS[control]
        if source.count(old) != 1:
            raise ValueError(f"{control}: expected exactly one replacement site")
        source = source.replace(old, new)
    return [{"write": "exporter.py", "content": source}]


def calibrate():
    """Use the F19 oracle loader, scripted edits and score_child with only these known programs."""
    oracle = hidden.Oracle.locate(HERE, "REPORT-1")
    files = {path: base64.b64encode(data).decode("ascii") for path, data in oracle.files.items()}
    controls = {}
    for name in ("good", *FAULTS):
        edits = steps(name)
        with tempfile.TemporaryDirectory(prefix="report-1-control-") as temporary:
            root = Path(temporary).resolve()
            tree = root / "tree"
            tree.mkdir()
            ScriptedArm().run(tree, {"steps": edits}, deadline_s=30)
            spec = {"files": files, "layout": None, "env": hidden.program_env(root)}
            results = score_child.score(spec, tree)["checks"]
        intended_failures = FAULTS[name][0] if name != "good" else ()
        expected = [(criterion, criterion not in intended_failures) for criterion in CRITERIA]
        if [(row["name"], row["ok"]) for row in results] != expected:
            raise ValueError(f"{name}: expected {expected}, got {results}")
        controls[name] = {"exporter_sha256": hashlib.sha256(edits[0]["content"].encode()).hexdigest(),
                          "checks": {row["name"]: row["ok"] for row in results}}
    return {"case": "REPORT-1", "instrument": "F19 score_child on fixed trusted scripts", "contained": False,
            "oracle_sha256": oracle.sha256, "controls": controls}


if __name__ == "__main__":
    print(json.dumps(calibrate(), indent=2))
