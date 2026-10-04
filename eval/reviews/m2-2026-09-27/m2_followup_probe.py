"""Independent follow-up probes for AEW M2 fixes. Run against the fixed checkout."""
from pathlib import Path
import sys

TESTS = Path(__file__).resolve().parent / 'AEW-M2-validation' / 'tests'
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / 'helpers'))

from aewflow import (create_investigation, create_unit, complete_investigation,
                     parent_review, parent_verify, plan_unit, sample_project)


def test_parent_acceptance_evidence_waits_for_its_dependency_output(tmp_path):
    p = sample_project(tmp_path)
    prerequisite = create_investigation(p, tmp_path, title='Prerequisite survey', cls=0)
    parent = create_unit(p, 'story', 'Dependent objective', cls=1,
                         extra=('--depends-on', f'{prerequisite}:evidence'))
    plan_unit(p, tmp_path, parent)
    child = create_investigation(p, tmp_path, title='Completed child', cls=0)
    complete_investigation(p, child)
    p.lead('work', 'move', child, '--parent', parent, '--reason', 'accept this result')
    early = _attempt(p, 'invoke', 'create', parent, '--role', 'reviewer')
    if early.returncode != 0:
        assert early.error['code'] == 'DEPENDENCY_UNSATISFIED', early.stderr
        return  # early refusal is the stronger safe outcome
    p.lead('review', 'ingest', parent, '--evidence', parent_review(p, parent))
    p.lead('verify', 'ingest', parent, '--evidence', parent_verify(p, parent))
    before = p.ok('gate', 'show', parent)['gates']
    assert before['review_r1']['status'] == 'CURRENT'
    assert before['verification_goal_backwards']['status'] == 'CURRENT'
    blocked = p.aew('work', 'close', parent, '--reason', 'gates passed',
                    '--token', p.token, '--expect-rev', str(p.rev()))
    assert blocked.error['code'] == 'DEPENDENCY_UNSATISFIED'
    complete_investigation(p, prerequisite)
    after = p.ok('gate', 'show', parent)['gates']
    assert after['review_r1']['status'] == 'CURRENT' and after['verification_goal_backwards']['status'] == 'CURRENT'
    close = p.aew('work', 'close', parent, '--reason', 'prerequisite finished',
                  '--token', p.token, '--expect-rev', str(p.rev()))
    assert close.returncode != 0, 'parent closed on review and verification that predate its prerequisite output'


def _attempt(p, *args):
    return p.aew(*args, '--token', p.token, '--expect-rev', str(p.rev()))


def test_started_nonmutating_move_refusal_preserves_parent(tmp_path):
    from aewflow import dispatch
    p = sample_project(tmp_path)
    upstream = create_investigation(p, tmp_path, title='Unfinished upstream')
    parent = create_unit(p, 'story', 'Depends on upstream', cls=0)
    p.lead('work', 'depend', parent, '--add', f'{upstream}:evidence', '--reason', 'upstream required')
    child = create_investigation(p, tmp_path, title='Consumer')
    dispatch(p, child)
    result = _attempt(p, 'work', 'move', child, '--parent', parent, '--reason', 'join scope')
    assert result.error['code'] == 'ILLEGAL_TRANSITION'
    assert p.ok('work', 'show', child)['control']['parent'] is None


def test_finished_child_blocks_late_parent_dependency_edit(tmp_path):
    p = sample_project(tmp_path)
    parent = create_unit(p, 'story', 'Dependent parent', cls=0)
    child = create_investigation(p, tmp_path, parent=parent, cls=0)
    complete_investigation(p, child)
    upstream = create_investigation(p, tmp_path, title='Unfinished prerequisite')
    result = _attempt(p, 'work', 'depend', parent, '--add', f'{upstream}:evidence', '--reason', 'late')
    assert result.error['code'] == 'ILLEGAL_TRANSITION'
    assert p.ok('work', 'show', parent)['control']['depends_on'] == []


def test_started_mutating_move_refusal_preserves_parent(tmp_path):
    from aewflow import create_planned_ticket, assign
    p = sample_project(tmp_path)
    upstream = create_planned_ticket(p, tmp_path, title='Upstream mutation', cls=0)
    parent = create_unit(p, 'story', 'Waits for upstream', cls=0)
    p.lead('work', 'depend', parent, '--add', f'{upstream}:mutating', '--reason', 'needs integrated upstream')
    child = create_planned_ticket(p, tmp_path, title='Consumer mutation', cls=0)
    assign(p, child)
    result = _attempt(p, 'work', 'move', child, '--parent', parent, '--reason', 'scope expanded')
    assert result.error['code'] == 'ILLEGAL_TRANSITION'
    assert p.ok('work', 'show', child)['control']['parent'] is None


def test_redispatch_respects_nonmutating_concurrency_after_ingest(tmp_path):
    from aewflow import dispatch, submit_record
    from aew.util import dump_yaml, load_yaml
    p = sample_project(tmp_path)
    policy = p.root / '.aew/policy/gates.yaml'
    gates = load_yaml(policy.read_text(encoding='utf-8'), source='gates')
    gates['non_mutating_concurrency'] = 1
    policy.write_text(dump_yaml(gates), encoding='utf-8')
    first = create_investigation(p, tmp_path, title='First')
    second = create_investigation(p, tmp_path, title='Second')
    role, _ = dispatch(p, first)
    record = submit_record(role, 'discovery_record')['evidence']
    p.lead('evidence', 'ingest', first, '--evidence', record)
    dispatch(p, second)
    result = _attempt(p, 'work', 'redispatch', first, '--reason', 'refresh first record')
    assert result.returncode != 0, 'redispatch exceeded the configured concurrency cap: ' + result.stdout
    assert result.error['code'] == 'CONCURRENCY_LIMIT', result.stderr


def test_redispatch_replacing_active_attempt_stays_within_cap(tmp_path):
    from aewflow import dispatch
    from aew.util import dump_yaml, load_yaml
    p = sample_project(tmp_path)
    policy = p.root / '.aew/policy/gates.yaml'
    gates = load_yaml(policy.read_text(encoding='utf-8'), source='gates')
    gates['non_mutating_concurrency'] = 1
    policy.write_text(dump_yaml(gates), encoding='utf-8')
    child = create_investigation(p, tmp_path)
    _, first = dispatch(p, child)
    second = p.lead('work', 'redispatch', child, '--reason', 'refresh')
    assert second['execution']['attempt'] == 2
    assert p.ok('invoke', 'show', first['invocation'])['status'] == 'superseded'
    assert p.ok('invoke', 'show', second['invocation'])['status'] == 'active'


def test_parent_acceptance_waits_at_dispatch_for_its_dependency(tmp_path):
    p = sample_project(tmp_path)
    prerequisite = create_investigation(p, tmp_path, title='Prerequisite survey', cls=0)
    parent = create_unit(p, 'story', 'Dependent objective', cls=1,
                         extra=('--depends-on', f'{prerequisite}:evidence'))
    plan_unit(p, tmp_path, parent)
    child = create_investigation(p, tmp_path, title='Completed child', cls=0)
    complete_investigation(p, child)
    p.lead('work', 'move', child, '--parent', parent, '--reason', 'accept this result')
    for role in ('reviewer', 'verifier'):
        result = _attempt(p, 'invoke', 'create', parent, '--role', role)
        assert result.error['code'] == 'DEPENDENCY_UNSATISFIED', result.stdout
    record = complete_investigation(p, prerequisite)
    review = p.lead('invoke', 'create', parent, '--role', 'reviewer')
    pinned = p.ok('invoke', 'show', review['invocation'])['inputs']
    assert any(item['id'] == record and item['from'] == prerequisite for item in pinned)
