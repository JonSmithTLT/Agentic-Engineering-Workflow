"""Independent P2b review probes; disposable fixture repositories only."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT / 'tests/helpers')]
os.environ['PYTHONPATH'] = str(ROOT / 'src')
from aewflow import sample_project, create_unit, plan_unit, create_investigation, dispatch, submit_record, close_parent
from conftest import run_aew, git
from invariants import load_control, assert_control_invariants
from history_model import init, archive
from aew.history.index import HistoryIndex

def emit(name, **values):
    print(json.dumps(dict(probe=name, **values)), flush=True)

def capture(p, *args):
    r = p.aew(*args)
    return dict(rc=r.returncode, stdout=r.stdout, stderr=r.stderr)

base = Path(tempfile.mkdtemp(prefix='probe-', dir=ROOT))
emit('source', source=str(ROOT), fixtures=str(base))

folder = base / 'hierarchy'
folder.mkdir()
p = sample_project(folder)
story = create_unit(p, 'story', 'Archived ancestor')
plan_unit(p, folder, story)
wid = create_investigation(p, folder, parent=story)
role, out = dispatch(p, wid)
rec = submit_record(role, 'discovery_record')['evidence']
p.lead('evidence', 'ingest', wid, '--evidence', rec)
p.lead('work', 'accept', wid)
emit('normal_cleanup', observation_exists=role.workspace.exists())
emit('cold_child_hot_parent', pack=capture(p, 'context', 'pack', out['invocation']), gate=capture(p, 'gate', 'show', wid))
close_parent(p, story)
assert_control_invariants(p)
emit('cold_child_cold_parent', pack=capture(p, 'context', 'pack', out['invocation']), gate=capture(p, 'gate', 'show', wid), harness=capture(p, 'harness', 'status', out['invocation']))

folder = base / 'crash'
folder.mkdir()
p = sample_project(folder)
wid = create_investigation(p, folder)
role, out = dispatch(p, wid)
assert role.workspace.exists()
r = run_aew('-C', str(p.root), 'work', 'transition', wid, '--to', 'CANCELLED', '--reason', 'crash during cancellation', '--token', p.token, '--expect-rev', str(p.rev()), env={'AEW_FAULT':'history.after_bundle'})
shown = p.ok('work', 'show', wid)
assert_control_invariants(p)
p.lead('checkpoint')
emit('crash_cleanup', crash_rc=r.returncode, archived=shown['control']['archived'], observation_exists=role.workspace.exists(), hot_invocation=out['invocation'] in load_control(p.root)['invocations'], worktrees=git('worktree', 'list', '--porcelain', cwd=p.root), resume=p.ok('resume', '--json'))
orphan = role.workspace
normal_wid = create_investigation(p, folder, title='Normal cancellation control')
normal_role, normal_out = dispatch(p, normal_wid)
p.lead('work', 'transition', normal_wid, '--to', 'CANCELLED', '--reason', 'positive control')
assert_control_invariants(p)
emit('normal_cancel_cleanup', normal_observation_exists=normal_role.workspace.exists(), old_orphan_exists=orphan.exists(), status=p.ok('status', '--json'))

folder = base / 'moves'
folder.mkdir()
p = sample_project(folder)
wid = create_investigation(p, folder)
role, out = dispatch(p, wid)
rec = submit_record(role, 'discovery_record')['evidence']
p.lead('evidence', 'ingest', wid, '--evidence', rec)
p.lead('work', 'accept', wid)
story = create_unit(p, 'story', 'New parent')
plan_unit(p, folder, story)
create_investigation(p, folder, parent=story)
p.lead('work', 'move', wid, '--parent', story, '--reason', 'review move')
assert_control_invariants(p)
emit('moved_listing', wid=wid, expected_parent=story, show=p.ok('work','show',wid)['control']['parent'], listing=p.ok('work','list','--state','DONE'), recent=p.ok('resume','--json')['finished']['recent'], tree=p.ok('work','tree'))

store = init(base / 'index')
old = archive(store)
idx = HistoryIndex(store.root)
idx.sync(old)
emit('index_old_control', list=[e['id'] for e in idx.list(limit=1)], links=idx.links('T-0001'), paths=sorted(idx.paths()))
new = archive(store)
idx.sync(new)
mode = idx.sync(old)
emit('index_ahead_snapshot', mode=mode, unlimited=[e['id'] for e in idx.list()], limited=[e['id'] for e in idx.list(limit=1)], links=idx.links('T-0001'), paths=sorted(idx.paths()))
