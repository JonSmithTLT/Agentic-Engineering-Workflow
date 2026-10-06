"""Probes from the M1 foundation review, preserved as regressions.

Provenance: AEW-M1-review-2026-09-26/foundation-review/test_foundation_probes.py (reviewed revision
f3fc4a3). The four probe bodies below are the reviewer's, unchanged; each asserts the SAFE behavior:
index-only work is never called clean (inspection, cleanup); an obligation added after validation is
enforced at publication; an evidence-only Ticket never mutates or publishes source in M1.
"""
from pathlib import Path

from aewflow import prepare_and_validate, sample_project, to_commit_ready
from conftest import git, make_git_repo

from aew.workspace import worktrees


def test_inspection_detects_index_only_work(tmp_path):
    repo = make_git_repo(tmp_path / 'repo', {'source.py': 'original\n'})
    head = git('rev-parse', 'HEAD', cwd=repo)
    (repo / 'source.py').write_text('valuable staged revision\n')
    git('add', 'source.py', cwd=repo)
    (repo / 'source.py').write_text('original\n')
    assert git('show', ':source.py', cwd=repo) == 'valuable staged revision'
    assert worktrees.inspect(str(repo), head)['dirty'] is not False, 'Inspection calls index-only work clean'


def test_done_cleanup_preserves_index_only_late_source(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    source = impl.workspace / 'calc/core.py'
    published_content = source.read_text()
    source.write_text(published_content + '\n# valuable staged late implementation\n')
    git('add', 'calc/core.py', cwd=impl.workspace)
    staged = git('show', ':calc/core.py', cwd=impl.workspace)
    source.write_text(published_content)
    assert git('diff', '--cached', '--name-only', cwd=impl.workspace) == 'calc/core.py'
    p.lead('integrate', 'publish', wid)
    assert impl.workspace.exists(), 'DONE cleanup deleted the workspace containing independent staged source'
    assert git('show', ':calc/core.py', cwd=impl.workspace) == staged


def test_publish_rechecks_new_required_role_gate(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    p.as_operator('work_staff', work_id=wid, review=['security_reviewer'], selected_by='operator', pin=True)
    gates = p.ok('gate', 'show', wid)
    assert gates['gates']['review_card:security_reviewer']['status'] == 'MISSING'
    result = p.aew('integrate', 'publish', wid, '--token', p.token, '--expect-rev', str(p.rev()))
    assert result.returncode != 0, ('Published DONE with an unfulfilled operator-pinned review obligation: '
                                    + result.stdout)


def test_non_mutating_ticket_cannot_publish_source_while_mutation_slot_is_busy(tmp_path):
    from aewflow import assign, create_planned_ticket
    p = sample_project(tmp_path)
    holder = create_planned_ticket(p, tmp_path, title='Legitimate mutation slot holder')
    assign(p, holder)
    wid = create_planned_ticket(p, tmp_path, title='Evidence-only work', extra=('--non-mutating',))
    # M1 may reject assignment of this unsupported path, or enforce evidence-only behavior.
    result = p.aew('work', 'assign', wid, '--token', p.token, '--expect-rev', str(p.rev()))
    if result.returncode:
        return
    from aewflow import Role, implement, review, verify
    impl = Role(p, result.json['invocation_token'], Path(result.json['workspace']['path']))
    p.lead('work', 'transition', wid, '--to', 'RUNNING')
    implement(impl)
    p.lead('work', 'transition', wid, '--to', 'REVIEW_PENDING')
    report = review(p, wid)
    p.lead('review', 'ingest', wid, '--evidence', report)
    p.lead('work', 'transition', wid, '--to', 'VERIFY_PENDING')
    report = verify(p, wid)
    p.lead('verify', 'ingest', wid, '--evidence', report)
    p.lead('work', 'transition', wid, '--to', 'COMMIT_READY')
    prepare_and_validate(p, wid)
    published = p.lead('integrate', 'publish', wid)
    assert p.ok('work', 'show', holder)['control']['workspace']['status'] == 'active'
    assert 'def subtract' not in (p.root / 'calc/core.py').read_text(), (
        'Evidence-only Ticket mutated and published source while another mutation workspace was active', published)
