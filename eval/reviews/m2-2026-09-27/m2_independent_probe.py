"""Independent AEW M2 regressions. Run with the AEW venv Python and pytest."""
from pathlib import Path
import sys

TESTS = Path(__file__).resolve().parent / 'Agentic-Engineering-Workflow' / 'tests'
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS / 'helpers'))

from aewflow import sample_project, create_unit, create_investigation, dispatch, plan_unit, submit_record


def _refusal(p, *args):
    result = p.aew(*args, '--token', p.token, '--expect-rev', str(p.rev()))
    assert result.returncode != 0, f'unsafe success: {result.stdout}'
    return result.error


def test_class0_descendant_cannot_complete_after_ancestor_first_plan(tmp_path):
    p = sample_project(tmp_path)
    parent = create_unit(p, 'story', 'Parent', cls=0)
    child = create_investigation(p, tmp_path, parent=parent, cls=0)
    role, _ = dispatch(p, child)
    plan_unit(p, tmp_path, parent, 'New parent intent.\n')
    record = submit_record(role, 'discovery_record')['evidence']
    p.lead('evidence', 'ingest', child, '--evidence', record)
    assert _refusal(p, 'work', 'redispatch', child, '--reason', 'check binding')['code'] == 'GATE_UNSATISFIED'
    _refusal(p, 'work', 'accept', child)


def test_move_cannot_let_running_child_bypass_inherited_dependency(tmp_path):
    p = sample_project(tmp_path)
    upstream = create_investigation(p, tmp_path, title='Unfinished upstream')
    parent = create_unit(p, 'story', 'Depends on upstream', cls=0)
    p.lead('work', 'depend', parent, '--add', f'{upstream}:evidence', '--reason', 'upstream required')
    child = create_investigation(p, tmp_path, title='Consumer', cls=1)
    role, _ = dispatch(p, child)
    p.lead('work', 'move', child, '--parent', parent, '--reason', 'join scope')
    p.lead('plan', 'reconfirm', child, '--reason', 'parent plan checked')
    record = submit_record(role, 'discovery_record')['evidence']
    p.lead('evidence', 'ingest', child, '--evidence', record)
    _refusal(p, 'work', 'accept', child)


def test_observation_mutated_after_submit_cannot_be_ingested(tmp_path):
    p = sample_project(tmp_path)
    child = create_investigation(p, tmp_path)
    role, _ = dispatch(p, child)
    record = submit_record(role, 'discovery_record')['evidence']
    (role.workspace / 'calc/core.py').write_text('tampered\n', encoding='utf-8')
    _refusal(p, 'evidence', 'ingest', child, '--evidence', record)


def test_parent_cannot_close_with_new_unsatisfied_dependency(tmp_path):
    from aewflow import complete_investigation
    p = sample_project(tmp_path)
    parent = create_unit(p, 'story', 'Dependent parent', cls=0)
    child = create_investigation(p, tmp_path, parent=parent, cls=0)
    complete_investigation(p, child)
    upstream = create_investigation(p, tmp_path, title='Unfinished prerequisite')
    p.lead('work', 'depend', parent, '--add', f'{upstream}:evidence', '--reason', 'needs prerequisite')
    _refusal(p, 'work', 'close', parent, '--reason', 'all work complete')


def test_class0_mutating_cannot_reach_commit_ready_under_stale_ancestor_plan(tmp_path):
    from aewflow import create_planned_ticket, assign, implement
    p = sample_project(tmp_path)
    parent = create_unit(p, 'story', 'Parent intent', cls=0)
    child = create_planned_ticket(p, tmp_path, cls=0, extra=('--parent', parent))
    role = assign(p, child)
    implement(role)
    plan_unit(p, tmp_path, parent, 'New parent intent.\n')
    _refusal(p, 'work', 'transition', child, '--to', 'COMMIT_READY')


def test_class0_mutating_cannot_prepare_integration_after_ancestor_replan(tmp_path):
    from aewflow import create_planned_ticket, assign, implement
    p = sample_project(tmp_path)
    parent = create_unit(p, 'story', 'Parent intent', cls=0)
    child = create_planned_ticket(p, tmp_path, cls=0, extra=('--parent', parent))
    role = assign(p, child)
    implement(role)
    p.lead('work', 'transition', child, '--to', 'COMMIT_READY')
    plan_unit(p, tmp_path, parent, 'New parent intent.\n')
    _refusal(p, 'integrate', 'prepare', child)


def test_class0_mutating_cannot_publish_after_ancestor_replan(tmp_path):
    from aewflow import create_planned_ticket, assign, implement, prepare_and_validate
    p = sample_project(tmp_path)
    parent = create_unit(p, 'story', 'Parent intent', cls=0)
    child = create_planned_ticket(p, tmp_path, cls=0, extra=('--parent', parent))
    role = assign(p, child)
    implement(role)
    p.lead('work', 'transition', child, '--to', 'COMMIT_READY')
    prepare_and_validate(p, child)
    plan_unit(p, tmp_path, parent, 'New parent intent.\n')
    _refusal(p, 'integrate', 'publish', child)


def test_index_only_observation_mutation_cannot_submit(tmp_path):
    from conftest import git
    p = sample_project(tmp_path)
    child = create_investigation(p, tmp_path)
    role, _ = dispatch(p, child)
    source = role.workspace / 'calc/core.py'
    original = source.read_text(encoding='utf-8')
    source.write_text('tampered\n', encoding='utf-8')
    git('add', 'calc/core.py', cwd=role.workspace)
    source.write_text(original, encoding='utf-8')
    assert git('diff', '--cached', '--name-only', cwd=role.workspace) == 'calc/core.py'
    result = submit_record(role, 'discovery_record', expect_ok=False)
    assert result.error['code'] == 'OBSERVATION_MUTATED'


def test_moved_mutating_ticket_cannot_publish_before_inherited_upstream_integrates(tmp_path):
    from aewflow import create_planned_ticket, assign, implement, prepare_and_validate
    p = sample_project(tmp_path)
    upstream = create_planned_ticket(p, tmp_path, title='Upstream mutation', cls=0)
    parent = create_unit(p, 'story', 'Waits for upstream', cls=0)
    p.lead('work', 'depend', parent, '--add', f'{upstream}:mutating', '--reason', 'needs integrated upstream')
    child = create_planned_ticket(p, tmp_path, title='Consumer mutation', cls=0)
    role = assign(p, child)
    implement(role)
    p.lead('work', 'move', child, '--parent', parent, '--reason', 'scope expanded')
    p.lead('plan', 'reconfirm', child, '--reason', 'parent reviewed')
    p.lead('work', 'transition', child, '--to', 'COMMIT_READY')
    prepare_and_validate(p, child)
    _refusal(p, 'integrate', 'publish', child)
