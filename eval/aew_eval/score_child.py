"""The scoring process of the hidden-evaluator channel: ``python -I -B score_child.py <checks.py> <tree>``.

It runs model-written code (the checks import and drive it), so it is its own process, isolated (``-I``: no
``PYTHONPATH``, no user site, not even this script's directory on the path) and importing only the standard library
before the tree joins the path. A file the model planted in the tree (a ``json.py``, an ``aew_eval/``) therefore cannot
replace anything this script uses; it can only be what the checks deliberately import. Prints one JSON line:
``{"passed", "checks": [{"name", "ok", "detail"}]}``.
"""

import importlib.util
import json
import sys
import traceback
from pathlib import Path


def run(checks_py: Path, tree: Path) -> dict:
    results = []
    sys.path.insert(0, str(tree))  # only now: everything this script needs is already imported
    try:
        spec = importlib.util.spec_from_file_location("aew_eval_oracle_checks", checks_py)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, ok, detail in module.checks(tree):
            results.append({"name": str(name), "ok": bool(ok), "detail": str(detail)[-600:]})
    except Exception:  # noqa: BLE001 (a broken check or broken model code is a failed check, recorded)
        results.append({"name": "checks raised", "ok": False, "detail": traceback.format_exc()[-1200:]})
    return {"passed": bool(results) and all(r["ok"] for r in results), "checks": results}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -I -B score_child.py <checks.py> <tree>", file=sys.stderr)
        sys.exit(2)
    sys.dont_write_bytecode = True
    out = run(Path(sys.argv[1]), Path(sys.argv[2]).resolve())
    sys.stdout.write("\n" + json.dumps(out) + "\n")
    sys.stdout.flush()
    import os

    os._exit(0)  # the result is the last line: no exit handler the model's code registered runs after it
