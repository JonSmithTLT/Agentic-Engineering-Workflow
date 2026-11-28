"""A candidate's public cases as F19 cases (skill evaluation guide §4 and §5, steps 2 and 3).

The guide's notation (``aew-skill-cases/v1``, each candidate's ``evals/cases.yaml``) holds both sides of a case in one
file: what the worker is given, and the evaluator's ``purpose``, ``split`` and ``oracle``. :func:`materialize` splits
them. Into the cases directory go F19 case manifests (``aew/eval-case/v1``) built from the ``worker`` mapping alone:
its ``artifacts`` as the fixture's base tree, and its ``task``, ``context``, ``capabilities`` and ``constraints`` as
the task. Into the evaluator's directory goes the key: each neutral case id's own id, split, expected activation and
oracle hash. An arm is given the first directory's content only; the key never enters a run.

A case id is neutral (``K01``, by the case's place in its file) because F19 writes the id into the starting commit's
subject: an id says which case this is, never which skill or answer it belongs to.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from aew_eval import fixture
from aew_eval.canonical import sha256_of
from aew_eval.schemas import Invalid

FORMAT = "aew-skill-cases/v1"
KEY = "aew/skill-eval-key/v1"
KEY_FILE = "key.json"
WORKER = ("task", "context", "artifacts", "capabilities", "constraints")  # the guide's worker mapping, all of it
ACTIVATIONS = ("use", "skip", "abstain")
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def read(path: Path) -> dict[str, Any]:
    """The cases file, held to the guide's notation: its format, its skill, and for every case an id of its own, a
    ``worker`` mapping of exactly the guide's fields and an ``oracle`` whose ``activation`` is one of the three."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise Invalid(f"{path} is not an {FORMAT} file")
    if not isinstance(data.get("skill"), str) or not isinstance(data.get("cases"), list) or not data["cases"]:
        raise Invalid(f"{path} names no skill or holds no cases")
    seen: set[str] = set()
    for n, case in enumerate(data["cases"], 1):
        where = f"{path} case {n}"
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in seen:
            raise Invalid(f"{where} has no id of its own")
        seen.add(case["id"])
        worker, oracle = case.get("worker"), case.get("oracle")
        if not isinstance(worker, dict) or set(worker) - set(WORKER) or not isinstance(worker.get("task"), str):
            raise Invalid(f"{where} ({case['id']}): worker is a mapping of {', '.join(WORKER)}, with a task")
        if not isinstance(oracle, dict) or oracle.get("activation") not in ACTIVATIONS:
            raise Invalid(f"{where} ({case['id']}): oracle.activation is one of {', '.join(ACTIVATIONS)}")
    return data


def task(worker: dict[str, Any], answer_file: str | None = None) -> str:
    """What a worker is given as its one message: the case's task, then its context, capabilities and constraints
    under plain headings, in the guide's order, and nothing else of the case. ``answer_file`` adds one sentence, the
    same for every case and arm, asking for the final answer in that file, so that the answer is in the exported tree
    a grader reads (README, "The answer")."""
    parts = [str(worker["task"]).strip()]
    if str(worker.get("context") or "").strip():
        parts.append("Context:\n" + str(worker["context"]).strip())
    for heading, key in (("Capabilities", "capabilities"), ("Constraints", "constraints")):
        items = [str(item).strip() for item in worker.get(key) or []]
        if items:
            parts.append(f"{heading}:\n" + "\n".join(f"- {item}" for item in items))
    if answer_file:
        parts.append(f"Write your final answer to `{answer_file}` in the working directory. That file is what is "
                     "read, and adding it changes none of the supplied files.")
    return "\n\n".join(parts) + "\n"


def neutral_ids(data: dict[str, Any]) -> dict[str, str]:
    """Each case's neutral id, by its place in the file, so that choosing a subset renames nothing."""
    return {case["id"]: f"K{n:02d}" for n, case in enumerate(data["cases"], 1)}


def materialize(source: Path, cases_dir: Path, evaluator_dir: Path, *, only: list[str] | None = None,
                answer_file: str | None = None) -> dict[str, Any]:
    """Write ``source``'s cases (all of them, or the ids in ``only``) as F19 cases under ``cases_dir`` and their key
    under ``evaluator_dir``; returns the key. Both directories are made afresh, and neither lies in the other.

    Each case's hash is F19's (:func:`aew_eval.fixture.case_sha256`), read back from what was written, so the
    ``cases`` block the key carries for a preregistration is what a run will check."""
    data = read(source)
    ids = neutral_ids(data)
    unknown = sorted(set(only or []) - set(ids))
    if unknown:
        raise Invalid(f"{source} has no case {', '.join(unknown)}")
    if answer_file is not None and not FILE_NAME.match(answer_file):
        raise Invalid(f"the answer file is a plain file name, not {answer_file!r}")
    here, there = cases_dir.resolve(), evaluator_dir.resolve()
    if here == there or here in there.parents or there in here.parents:
        raise Invalid("the cases directory and the evaluator's directory are apart: neither lies in the other")
    for folder in (cases_dir, evaluator_dir):
        if folder.exists():
            raise Invalid(f"{folder} exists: cases are materialized into fresh directories")
    chosen = [case for case in data["cases"] if only is None or case["id"] in only]
    # where the source is, so a run can require its directory (the oracles, the rubric) hidden from a contained arm
    key: dict[str, Any] = {"schema": KEY, "skill": data["skill"], "source": source.name,
                           "source_dir": str(source.parent.resolve()),
                           "source_sha256": hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
                           "answer_file": answer_file, "cases": {}, "preregistration_cases": []}
    for case in chosen:
        worker, neutral = case["worker"], ids[case["id"]]
        artifacts = worker.get("artifacts") or {}
        if not isinstance(artifacts, dict) or not artifacts or not all(isinstance(v, str) for v in artifacts.values()):
            raise Invalid(f"case {case['id']} supplies no artifact files as text: F19 builds a case from a fixture "
                          "tree, so leave it out (only) or give it one")
        if answer_file is not None and answer_file.casefold() in {str(rel).casefold() for rel in artifacts}:
            raise Invalid(f"case {case['id']} supplies a file named {answer_file}: choose another answer file")
        root = cases_dir / neutral
        for rel, text in artifacts.items():
            out = root / "base" / fixture.safe_relative(str(rel), f"case {case['id']} artifact")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(text.encode("utf-8"))  # the literal bytes, as the guide asks (step 3)
        manifest = {"schema": fixture.CASE, "id": neutral, "family": data["skill"], "task": task(worker, answer_file),
                    "fixture": {"base": "base"}, "hidden_sha256": None, "control_of": None}
        (root / "case.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=120),
                                        encoding="utf-8", newline="\n")
        digest = fixture.case_sha256(fixture.load(root / "case.yaml"))
        key["cases"][neutral] = {"id": case["id"], "split": case.get("split"),
                                 "activation": case["oracle"]["activation"], "oracle_sha256": sha256_of(case["oracle"])}
        key["preregistration_cases"].append({"id": neutral, "family": data["skill"], "sha256": digest,
                                             "hidden_sha256": None, "control_of": None})
    evaluator_dir.mkdir(parents=True)
    (evaluator_dir / KEY_FILE).write_text(json.dumps(key, indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                          newline="\n")
    return key


def manifests(cases_dir: Path) -> dict[str, Path]:
    """Every materialized case's manifest, by its id: what :func:`aew_eval.runner.run_cell` takes as ``cases``."""
    return {path.parent.name: path for path in sorted(cases_dir.glob("*/case.yaml"))}


def load_key(evaluator_dir: Path) -> dict[str, Any]:
    key = json.loads((evaluator_dir / KEY_FILE).read_text(encoding="utf-8"))
    if not isinstance(key, dict) or key.get("schema") != KEY:
        raise Invalid(f"{evaluator_dir / KEY_FILE} is not an {KEY} record")
    return key
