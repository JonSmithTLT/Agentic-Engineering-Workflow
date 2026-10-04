"""Independent review probes for AEW 1d914cb, preserved as regressions.

Provenance: AEW M1 independent technical review, 2026-09-26
(AEW-M1-review-2026-09-26/REPORT.md, reproductions/test_review_regressions.py).
The probe bodies below are the reviewer's, unchanged; each asserts the SAFE
behavior. Findings still open are marked xfail(strict=True) and the marker is
removed by the commit that fixes the finding (see
docs/archive/reviews/review-response-2026-09-26.md).
"""
import pytest
from aewflow import (
    SUBTRACT_PATCH,
    assign,
    create_planned_ticket,
    implement,
    prepare_and_validate,
    redispatch_implementer,
    review,
    sample_project,
    to_commit_ready,
    to_verified,
    verify,
)
from conftest import IS_WINDOWS, Project, git, make_git_repo

from aew.workspace import integration as integration_git


def unit(p, wid):
    return p.ok('work', 'show', wid)['control']


def main(p):
    return git('rev-parse', 'refs/heads/main', cwd=p.root)


def pending_publish(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    result = p.aew('integrate', 'publish', wid, '--token', p.token,
                   '--expect-rev', str(p.rev()),
                   env={'AEW_FAULT': 'integrate.after_publishing_record'})
    assert result.returncode == 86
    assert main(p) == integ['base']
    return p, wid, impl, integ


def replan(p, wid, tmp_path):
    p.lead('work', 'transition', wid, '--to', 'REPLAN_REQUIRED', '--reason', 'revise approach')
    plan = tmp_path / 'revised-plan.md'
    plan.write_text('Use the revised approach and validate it.\n')
    p.lead('plan', 'propose', '--assurance', 'none', wid, '--file', str(plan), '--reason', 'new requirement')
    p.lead('plan', 'accept', wid, '--revision', '2')


def test_old_candidate_cannot_discard_newly_verified_implementation(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    old = prepare_and_validate(p, wid)
    p.lead('work', 'transition', wid, '--to', 'RUNNING', '--reason', 'additional required behavior')
    impl = redispatch_implementer(p, wid)
    files = dict(SUBTRACT_PATCH)
    files['calc/core.py'] += '\ndef multiply(a, b):\n    return a * b\n'
    files['tests/test_multiply.py'] = ('from calc.core import multiply\n\n'
                                      'def test_multiply():\n    assert multiply(3, 4) == 12\n')
    implement(impl, files)
    p.lead('work', 'transition', wid, '--to', 'REVIEW_PENDING')
    p.lead('review', 'ingest', wid, '--evidence', review(p, wid))
    p.lead('work', 'transition', wid, '--to', 'VERIFY_PENDING')
    p.lead('verify', 'ingest', wid, '--evidence', verify(p, wid))
    p.lead('work', 'transition', wid, '--to', 'COMMIT_READY')
    u = unit(p, wid)
    assert (u['commit_ready_snapshot']['relevant_inputs_fingerprint']
            != old['candidate_snapshot']['relevant_inputs_fingerprint'])
    result = p.aew('integrate', 'publish', wid, '--token', p.token, '--expect-rev', str(p.rev()))
    if result.returncode != 0:
        assert impl.workspace.exists()
        return
    assert unit(p, wid)['state'] == 'DONE'
    assert 'def multiply' in (p.root / 'calc/core.py').read_text(), (
        'DONE published the old candidate and deleted the newly verified workspace',
        result.json, impl.workspace.exists())


def test_stale_reconcile_cannot_move_authoritative_ref(tmp_path):
    p, wid, impl, integ = pending_publish(tmp_path)
    revision = p.rev()
    result = p.aew('integrate', 'reconcile', wid, '--token', p.token,
                   '--expect-rev', str(revision - 1))
    assert result.error['code'] == 'STALE_REVISION'
    assert main(p) == integ['base'], 'Rejected stale-revision command nevertheless published its candidate'


# On Windows the probe's text-mode write_text() stores CRLF, which the pre-fix code also refused;
# the LF-exact variant is tests/integration/test_worktree_sync.py::test_staged_independent_edit_*.
def test_reconcile_preserves_independent_staged_edit(tmp_path):
    p, wid, impl, integ = pending_publish(tmp_path)
    path = p.root / 'calc/core.py'
    staged = 'def add(a, b):\n    return a + b\n# independent staged work\n'
    path.write_text(staged)
    git('add', 'calc/core.py', cwd=p.root)
    path.write_text(git('show', f"{integ['candidate']}:calc/core.py", cwd=p.root) + '\n')
    result = p.aew('integrate', 'reconcile', wid, '--token', p.token, '--expect-rev', str(p.rev()))
    assert git('show', ':calc/core.py', cwd=p.root) == staged.strip(), (
        'Reconciliation destroyed a staged edit made after publication intent', result.stdout, result.stderr)


@pytest.mark.skipif(IS_WINDOWS, reason="needs a filemode-aware (POSIX) checkout")
def test_sync_handles_executable_bit_only_change(tmp_path):
    repo = make_git_repo(tmp_path / 'repo', {'run.sh': '#!/bin/sh\necho ok\n'})
    git('config', 'core.filemode', 'true', cwd=repo)
    base = git('rev-parse', 'HEAD', cwd=repo)
    (repo / 'run.sh').chmod(0o755)
    git('add', 'run.sh', cwd=repo)
    git('commit', '-qm', 'make executable', cwd=repo)
    candidate = git('rev-parse', 'HEAD', cwd=repo)
    git('reset', '--hard', base, cwd=repo)
    integration_git.precheck_sync(repo, base, ['run.sh'])
    integration_git.cas_publish(repo, 'refs/heads/main', candidate, base, 'review probe')
    integration_git.sync_worktree(repo, base, candidate, ['run.sh'])
    assert (repo / 'run.sh').stat().st_mode & 0o111


def test_replanned_active_workspace_still_counts_against_serial_cap(tmp_path):
    p = sample_project(tmp_path)
    first = create_planned_ticket(p, tmp_path)
    assign(p, first)
    replan(p, first, tmp_path)
    second = create_planned_ticket(p, tmp_path, title='Second mutating ticket')
    result = p.aew('work', 'assign', second, '--token', p.token, '--expect-rev', str(p.rev()))
    first_u = unit(p, first)
    old_active = p.ok('invoke', 'show', first_u['implementer_invocation'])['status'] == 'active'
    assert result.returncode != 0 or not old_active, (
        'Both mutating invocations are active even though the configured cap is one', first_u['state'])


def test_reassignment_does_not_retarget_old_invocation_credential(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    original = assign(p, wid)
    old_workspace_id = unit(p, wid)['workspace']['id']
    replan(p, wid, tmp_path)
    replacement = p.lead('work', 'assign', wid)
    result = original.aew('check', 'run', 'guardrails')
    assert result.returncode != 0 or result.json['evaluated_snapshot']['workspace_id'] == old_workspace_id, (
        'Old credential ran a check against the replacement workspace', result.stdout,
        replacement['workspace']['id'])


def test_pinning_existing_card_updates_constraint(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    p.lead('work', 'staff', wid, '--execute', 'c_engineer')
    p.lead('work', 'staff', wid, '--execute', 'c_engineer', '--by', 'operator', '--pin')
    selected = unit(p, wid)['role_plan']['execute'][0]
    assert selected['selected_by'] == 'operator' and selected['pinned'], selected


def test_explicit_dispatch_cannot_bypass_operator_pin(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    p.lead('work', 'staff', wid, '--execute', 'c_engineer', '--by', 'operator', '--pin')
    assign(p, wid)
    p.lead('invoke', 'cancel', unit(p, wid)['implementer_invocation'], '--reason', 'fresh bounded attempt')
    result = p.aew('invoke', 'create', wid, '--card', 'python_engineer',
                   '--token', p.token, '--expect-rev', str(p.rev()))
    assert result.returncode != 0, 'Dispatch silently bypassed the operator pin without reason or decision'


def test_assume_unchanged_source_invalidates_verified_gates(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_verified(p, tmp_path)
    git('add', 'calc/core.py', cwd=impl.workspace)
    git('update-index', '--assume-unchanged', 'calc/core.py', cwd=impl.workspace)
    before = p.ok('gate', 'show', wid)['snapshot']['relevant_inputs_fingerprint']
    (impl.workspace / 'calc/core.py').write_text('def subtract(a, b):\n    return 999\n')
    after = p.ok('gate', 'show', wid)
    result = p.aew('work', 'transition', wid, '--to', 'COMMIT_READY',
                   '--token', p.token, '--expect-rev', str(p.rev()))
    assert after['snapshot']['relevant_inputs_fingerprint'] != before and result.returncode != 0, (
        'Broken source retained CURRENT evidence and reached COMMIT_READY', after['unmet'], result.stdout)


def test_submitted_review_is_not_counted_as_ingested(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    p.lead('work', 'staff', wid, '--review', 'code_reviewer', '--review', 'security_reviewer')
    impl = assign(p, wid)
    implement(impl)
    p.lead('work', 'transition', wid, '--to', 'REVIEW_PENDING')
    security = review(p, wid, card='security_reviewer')
    code = review(p, wid, card='code_reviewer')
    p.lead('review', 'ingest', wid, '--evidence', code)
    u = unit(p, wid)
    assert not any(e['id'] == security for e in u['evidence'])
    assert u['state'] == 'REVIEW_PENDING', (
        'Unaccepted required security review was used to advance the state', u['state'], security)


def test_first_resume_after_manifest_crash_exposes_recovered_authority(tmp_path):
    repo = make_git_repo(tmp_path / 'repo', {'README.md': '# fixture\n', 'docs/adr/0001.md': '# decision\n'})
    p = Project(repo)
    candidates = p.ok('init')['authority_candidates']
    candidate = next(c for c in candidates if c['path'] == 'docs/adr/')
    p.token = p.ok('lead', 'acquire', '--expect-rev', '0')['token']
    result = p.aew('authority', 'accept', candidate['id'], '--class', 'decisions',
                   '--token', p.token, '--expect-rev', str(p.rev()),
                   env={'AEW_FAULT': 'txn.after_replace'})
    assert result.returncode == 86
    first = p.ok('resume', '--json')
    second = p.ok('authority', 'list')
    assert second['accepted']
    assert first['accepted_authority'] == second['accepted'], (
        'First reconstruction omitted committed authority and reported no contradiction', first['contradictions'])


def test_interruption_does_not_bypass_failure_classification(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    p.lead('work', 'transition', wid, '--to', 'REVIEW_PENDING')
    p.lead('review', 'ingest', wid, '--evidence', review(p, wid))
    p.lead('work', 'transition', wid, '--to', 'VERIFY_PENDING')
    p.lead('invoke', 'create', wid, '--role', 'verifier')
    failing = verify(p, wid, goal_result='fail')
    p.lead('verify', 'ingest', wid, '--evidence', failing)
    assert unit(p, wid)['state'] == 'VERIFICATION_FAILED'
    offer = p.lead('lead', 'handoff', 'offer')['offer']
    p.token = p.ok('lead', 'handoff', 'accept', '--offer', offer,
                   '--expect-rev', str(p.rev()))['token']
    result = p.aew('work', 'reconcile', wid, '--to', 'RUNNING', '--reason', 'inspect after interruption',
                   '--token', p.token, '--expect-rev', str(p.rev()))
    after = unit(p, wid)
    assert result.returncode != 0 or after['classifications'], (
        'Verification failure returned to mutation without classification', after['state'], after['classifications'])
