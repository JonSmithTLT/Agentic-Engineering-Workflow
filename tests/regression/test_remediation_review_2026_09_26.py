"""Follow-up probes from the focused re-review of the M1 remediation, preserved as regressions.

Provenance: AEW-M1-review-2026-09-26/remediation-review/REPORT.md and test_neighbor_paths.py
(reviewed revision e7e723c). The probe bodies below are the reviewer's, unchanged; each asserts
the SAFE behavior. Findings still open are marked xfail(strict=True); the commit fixing each one
removes its marker (see docs/archive/reviews/review-response-2026-09-26.md, re-review section).
"""
from pathlib import Path

import pytest
from aewflow import prepare_and_validate, sample_project, to_commit_ready, to_verified, verify
from conftest import git, make_git_repo

from aew.errors import AEWError
from aew.workspace import integration as I


def unit(p, wid):
    return p.ok('work', 'show', wid)['control']


def test_done_cleanup_preserves_assume_unchanged_late_source(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    git('update-index', '--assume-unchanged', 'calc/core.py', cwd=impl.workspace)
    late = 'def add(a, b):\n    return a + b\n# valuable late work\n'
    (impl.workspace / 'calc/core.py').write_text(late)
    p.lead('integrate', 'publish', wid)
    assert (impl.workspace / 'calc/core.py').exists(), 'DONE cleanup deleted hidden late source changes'
    assert (impl.workspace / 'calc/core.py').read_text() == late


@pytest.mark.parametrize('staged', [False, True])
def test_directory_to_file_sync_preserves_independent_descendant(tmp_path, staged):
    repo = make_git_repo(tmp_path / 'repo', {'pkg/old.txt': 'old\n', 'README': 'readme\n'})
    base = git('rev-parse', 'HEAD', cwd=repo)
    git('checkout', '-qb', 'candidate', cwd=repo)
    (repo / 'pkg/old.txt').unlink()
    (repo / 'pkg').rmdir()
    (repo / 'pkg').write_text('replacement file\n')
    git('add', '-A', cwd=repo)
    git('commit', '-qm', 'directory becomes file', cwd=repo)
    candidate = git('rev-parse', 'HEAD', cwd=repo)
    git('checkout', '-q', 'main', cwd=repo)
    paths = I.changed_between(repo, base, candidate)
    local = repo / 'pkg/local.txt'
    local.write_text('independent local work\n')
    if staged:
        git('add', 'pkg/local.txt', cwd=repo)
    try:
        I.precheck_sync(repo, base, paths)
        I.cas_publish(repo, 'refs/heads/main', candidate, base, 'probe')
        I.sync_worktree(repo, base, candidate, paths)
    except AEWError:
        pass
    assert local.is_file() and local.read_text() == 'independent local work\n', (
        'directory-to-file checkout destroyed a descendant absent from changed_paths', staged, paths)
    if staged:
        assert git('show', ':pkg/local.txt', cwd=repo) == 'independent local work'


def test_superseded_plan_integration_report_cannot_validate_new_candidate(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    old = p.lead('integrate', 'prepare', wid)['integration']
    old_report = verify(p, wid, scope='integration')  # submitted for v1, NOT ingested
    p.lead('work', 'transition', wid, '--to', 'REPLAN_REQUIRED', '--reason', 'new acceptance requirements')
    plan = tmp_path / 'plan-v2.md'
    plan.write_text('Reassess the existing implementation against revised acceptance requirements.\n')
    p.lead('plan', 'propose', '--assurance', 'none', wid, '--file', str(plan),
           '--reason', 'new acceptance requirements')
    p.lead('plan', 'accept', wid, '--revision', '2')
    to_verified(p, tmp_path, wid=wid)
    p.lead('work', 'transition', wid, '--to', 'COMMIT_READY')
    new = p.lead('integrate', 'prepare', wid)['integration']
    assert old['workspace_id'] != new['workspace_id']
    assert (old['candidate_snapshot']['relevant_inputs_fingerprint']
            == new['candidate_snapshot']['relevant_inputs_fingerprint'])
    result = p.aew('verify', 'ingest', wid, '--evidence', old_report, '--token', p.token, '--expect-rev', str(p.rev()))
    publication = p.lead('integrate', 'publish', wid) if result.returncode == 0 else None
    assert result.returncode != 0, (
        'Old-plan evidence from a revoked invocation validated and published the replacement candidate',
        old['binding'], new['binding'], result.stdout, publication)


def test_long_lived_role_catalog_refreshes_adopted_manifest(tmp_path):
    from aew.engine.api import Engine
    from aew.util import dump_yaml, read_yaml
    p = sample_project(tmp_path)
    engine = Engine.discover(p.root)
    assert 'special_engineer' not in {c['id'] for c in engine.role_list()['cards']}
    new_catalog = p.root / '.aew/new-roles'
    new_catalog.mkdir()
    card = {'schema': 'aew/role/v1', 'role': 'special_engineer', 'display_name': 'Special',
            'extends': 'implementer', 'purpose': 'specific implementation'}
    (new_catalog / 'special.yaml').write_text(dump_yaml(card))
    manifest_path = p.root / '.aew/project.yaml'
    manifest = read_yaml(manifest_path)
    manifest.setdefault('roles', {})['catalog'] = 'new-roles/'
    manifest_path.write_text(dump_yaml(manifest))
    p.adopt_policy('use new role catalog')
    assert 'special_engineer' in {c['id'] for c in Engine.discover(p.root).role_list()['cards']}
    cards = {c['id'] for c in engine.role_list()['cards']}
    assert 'special_engineer' in cards, 'Long-lived role_list still uses the previous manifest'


def test_retiring_candidate_revokes_its_verifier_submission_authority(tmp_path):
    from aewflow import Role

    from aew.util import dump_yaml
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    old = p.lead('integrate', 'prepare', wid)['integration']
    invocation = p.lead('invoke', 'create', wid, '--role', 'verifier', '--scope', 'integration')
    old_role = Role(p, invocation['invocation_token'], Path(old['workspace']))
    check = old_role.check('unit')['evidence']
    p.lead('work', 'transition', wid, '--to', 'RUNNING', '--reason', 'supersede candidate')
    assert unit(p, wid)['integration'] is None
    submission = tmp_path / 'superseded-verifier-report.md'
    meta = {'verification': {'scope': 'integration', 'claims': [
        {'type': 'goal_backwards', 'claim': 'old candidate passed', 'result': 'pass', 'checks': [check]}]}}
    submission.write_text('---\n' + dump_yaml(meta) + '---\n')
    result = p.aew('submit', '--kind', 'verification', '--file', str(submission),
                   env={'AEW_INVOCATION_TOKEN': invocation['invocation_token']})
    assert result.returncode != 0, 'Retired-candidate invocation still has submission authority'
