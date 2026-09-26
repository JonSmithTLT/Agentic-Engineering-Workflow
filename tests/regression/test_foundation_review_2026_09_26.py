"""Index-only-work probes from the M1 foundation review, preserved as regressions.

Provenance: AEW-M1-review-2026-09-26/foundation-review/test_foundation_probes.py (reviewed revision
f3fc4a3). The two probe bodies below are the reviewer's, unchanged; each asserts the SAFE behavior:
a change that exists only in the Git index is work, and inspection/cleanup must not call it clean.
"""
from pathlib import Path
from conftest import git, make_git_repo
from aewflow import sample_project, to_commit_ready, prepare_and_validate
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
