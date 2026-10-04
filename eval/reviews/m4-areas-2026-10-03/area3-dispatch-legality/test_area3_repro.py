"""Area 3 (dispatch legality) reproductions against the frozen tree at a6cdc64.

Run from the review folder:
    venv/Scripts/python -m pytest repro/test_area3_repro.py -q -p no:cacheprovider --rootdir repro -s
"""

from __future__ import annotations

import _env  # noqa: F401
from aewflow import sample_project

from aew.util import parse_frontmatter, render_frontmatter

ALL_ASSERTIONS = ("--class0-assert", "transformation_clear", "--class0-assert", "inputs_complete",
                  "--class0-assert", "no_consequential_boundary")


def ticket(p, tmp_path, *, cls=1, scope=("calc/**", "tests/**"), extra=(), affected=("calc/core.py",),
           non_mutating=False):
    args = ["work", "create", "ticket", "--title", "Add subtract()", "--class", str(cls),
            "--goal", "calc.core.subtract(5, 3) == 2", *(["--non-mutating"] if non_mutating else []), *extra]
    for s in scope:
        args += ["--scope", s]
    wid = p.lead(*args)["id"]
    plan = tmp_path / f"{wid}-plan.md"
    plan.write_text("Add subtract and a focused test.\n", encoding="utf-8")
    more = [a for path in affected for a in ("--affected", path)]
    p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), *more)
    p.lead("plan", "accept", wid, "--revision", "1")
    return wid


def refused(p, *args):
    rev = p.rev()
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(rev))
    assert res.returncode != 0, res.stdout
    assert p.rev() == rev
    return res.error


def codes(err):
    return set(err["details"]["reason_codes"])


def edit_frontmatter(path, change):
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    change(meta)
    path.write_text(render_frontmatter(meta, body), encoding="utf-8", newline="\n")


# R1 ------------------------------------------------------------------------------------------------------------------

def test_r1_the_predicate_reads_the_ticket_record_and_plan_without_checking_their_recorded_hashes(tmp_path):
    """assurance_ops.py:46-57 + evidence_ops.py:86-87 + knowledge/records.py:147-150: Class 0 eligibility, the
    acceptance checks, the mutation scope and the plan's affected paths are read from files whose hashes control
    state records (record_sha256, plan.sha256) but which the predicate never compares. `status` reports the edit
    as a contradiction; dispatch admits on the edited content."""
    p = sample_project(tmp_path)
    # Class 0 without the Lead's assertions: refused, as designed
    wid = ticket(p, tmp_path, cls=0, scope=("calc/core.py",), extra=("--acceptance-check", "unit"))
    assert codes(refused(p, "work", "assign", wid)) == {"CLASS0_ASSERTION_MISSING"}
    # the record file gains the assertions out of band; control state still pins the old hash
    record = p.root / ".aew" / p.ok("work", "show", wid)["control"]["record"]
    edit_frontmatter(record, lambda m: m.update(class0_assertions=["inputs_complete", "no_consequential_boundary",
                                                                      "transformation_clear"]))
    contradictions = p.ok("status", "--json")["contradictions"]
    assert any("record" in c and "modified" in c for c in contradictions), contradictions
    explained = p.ok("dispatch", "explain", wid, "--json")
    assert explained["allowed"] is True                     # the predicate believes the edited file
    out = p.lead("work", "assign", wid)                     # ... and the commit check admits what it checked
    assert out["dispatch"]["allowed"] and out["invocation"].startswith("INV-")
    print(f"R1a: Class 0 admitted after editing the record file; status said: {contradictions[0]}")

    # the plan: an affected protected path refuses dispatch until the plan file is edited out of band
    p2 = sample_project(tmp_path / "second")
    wid2 = ticket(p2, tmp_path, affected=("calc/core.py", "vendor/lib.py"))
    assert "LINT_AFFECTED_PROTECTED" in codes(refused(p2, "work", "assign", wid2))
    plan_rel = p2.ok("work", "show", wid2)["control"]["plan"]["path"]
    edit_frontmatter(p2.root / ".aew" / plan_rel, lambda m: m.update(affected_paths=["calc/core.py"]))
    assert any("plan" in c and "modified" in c for c in p2.ok("status", "--json")["contradictions"])
    out = p2.lead("work", "assign", wid2)
    assert out["dispatch"]["allowed"]
    print("R1b: assignment admitted after editing the accepted plan's affected paths")


# R2 ------------------------------------------------------------------------------------------------------------------

def test_r2_class0_bounded_subject_is_a_denylist_of_five_strings(tmp_path):
    """assurance.py:30 + 108-112: a scope is 'unbounded' only if it is one of five literal catch-alls or matches no
    tracked file. `**/*.py` (every Python file in the repository) passes as a bounded subject."""
    # a project whose policy protects nothing (the fixture's vendor/** protection would otherwise catch this scope
    # through the protected-overlap guard, not through the boundedness check)
    p = sample_project(tmp_path, guardrails={"schema": "aew/guardrails/v1", "protected_paths": [],
                                             "generated_paths": [], "ticket_scope_enforcement": True,
                                             "review_triggers": [], "dependency_rules": []})
    wide = ticket(p, tmp_path, cls=0, scope=("**/*.py",), extra=("--acceptance-check", "unit", *ALL_ASSERTIONS))
    out = p.lead("work", "assign", wide)
    assert out["dispatch"]["allowed"] and out["dispatch"]["effective_obligations"] == []
    # for contrast, the literal catch-all is refused
    p2 = sample_project(tmp_path / "second")
    literal = ticket(p2, tmp_path, cls=0, scope=("**",), extra=("--acceptance-check", "unit", *ALL_ASSERTIONS))
    assert "CLASS0_SUBJECT_UNBOUNDED" in codes(refused(p2, "work", "assign", literal))


# R3 ------------------------------------------------------------------------------------------------------------------

def test_r3_an_acceptance_check_declared_on_a_non_mutating_ticket_never_becomes_a_gate(tmp_path):
    """work_ops.py:317-319 accepts --acceptance-check for any Ticket; with_acceptance_checks (gates.py:48-55) is
    applied only in the mutating gate context (evidence_ops.py:166), so on a non-mutating Ticket the declared check
    is recorded and ignored."""
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, cls=1, non_mutating=True, extra=("--acceptance-check", "unit"))
    shown = p.ok("gate", "show", wid)
    assert "acceptance_checks" not in shown["obligations"]["gates"], shown["obligations"]
    assert "acceptance_checks" not in shown["obligations"]["non_waivable"]
    record = p.root / ".aew" / p.ok("work", "show", wid)["control"]["record"]
    meta, _ = parse_frontmatter(record.read_text(encoding="utf-8"))
    assert meta["acceptance"]["checks"] == ["unit"]            # recorded on the Ticket, evaluated nowhere
