"""Independent public-operation probes against the archived P3 source only."""
import copy
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'tests/helpers'), str(ROOT/'tests/integration'), str(ROOT/'tools/perf')]
import aew
assert Path(aew.__file__).resolve().is_relative_to(ROOT/'src')
assert Path(sys.executable).resolve().is_relative_to(ROOT/'.venv')
if sys.platform == 'win32':
    popen = subprocess.Popen
    def hidden(*args, **kw):
        kw['creationflags'] = kw.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        return popen(*args, **kw)
    subprocess.Popen = hidden

from aew.engine.api import Engine
from aew.history.store import History
from aew.util import dump_yaml, load_yaml, sha256_bytes, sha256_file
from aewflow import sample_project, create_investigation, dispatch
from test_history_surface import finished_ticket
from invariants import load_control, assert_control_invariants
import control_plane as CP

def emit(name, **values):
    print(json.dumps(dict(probe=name, **values)), flush=True)

folder = Path(tempfile.mkdtemp(prefix='review-p3-fixtures-', dir=ROOT))
emit('environment', source=str(aew.__file__), interpreter=sys.executable, fixtures=str(folder))

# A syntactically healthy cache, with original root metadata, must not be able to
# substitute the payload pin of an entry whose real manifest and bundle stay intact.
tmp = folder/'cache-forgery'
tmp.mkdir()
p = sample_project(tmp)
wid, inv, rec = finished_ticket(p, tmp, title='Actual immutable survey')
shown = p.ok('history', 'show', wid)
db = p.root/'.aew/local/history.sqlite'
authority_before = load_control(p.root)['cold']['root']
real = p.root/'.aew/work'/wid/'archive.yaml'
real_sha = sha256_file(real)
with sqlite3.connect(db) as conn:
    entry = json.loads(conn.execute('SELECT body FROM entries WHERE id=?', (wid,)).fetchone()[0])
    forged = copy.deepcopy(load_yaml(real.read_text(encoding='utf-8')))
    forged['unit']['title'] = 'FORGED ENGINE HISTORY FROM LOCAL CACHE'
    forged['unit']['mutating'] = True
    forged['unit']['integration'] = {'commit': 'a'*40}
    fakepath = p.root/'.aew/local/forged-archive.yaml'
    fakepath.write_text(dump_yaml(forged), encoding='utf-8', newline='\n')
    entry['path'] = 'local/forged-archive.yaml'
    entry['sha256'] = sha256_file(fakepath)
    conn.execute('UPDATE entries SET body=?,path=?,sha256=? WHERE id=?',
                 (json.dumps(entry), entry['path'], entry['sha256'], wid))
conn.close()
fake_show = p.ok('history', 'show', wid)
audited = p.ok('history', 'audit', '--full')
consumer = create_investigation(p, tmp, title='Use historical source')
loaded = p.lead('history', 'load', wid, '--into', consumer, '--reason', 'exact source')
role, dispatch_out = dispatch(p, consumer)
state = load_control(p.root)
pack = (p.root/'.aew'/state['invocations'][dispatch_out['invocation']]['pack']['path']).read_text(encoding='utf-8')
dependent = create_investigation(p, tmp, title='Depend on completed source', extra=('--depends-on', f'{wid}:evidence'))
facts = load_control(p.root)['archived_refs'][wid]
db.unlink()
rebuilt_show = p.ok('history', 'show', wid)
emit('cache_substitutes_authority', actual_title=shown['record']['unit']['title'],
     substituted_title=fake_show['record']['unit']['title'], trust=fake_show['trust'],
     authoritative_bundle_unchanged=sha256_file(real)==real_sha,
     cold_root_unchanged=load_control(p.root)['cold']['root']==authority_before,
     full_audit=audited, loaded_sha=loaded['loaded']['sha256'], actual_sha=real_sha,
     substituted_pack='FORGED ENGINE HISTORY FROM LOCAL CACHE' in pack,
     committed_dependency_facts=facts, restored_title=rebuilt_show['record']['unit']['title'])
if '--cache-only' in sys.argv:
    raise SystemExit(0)

# Count verified history entries, not wall times, on current read paths after
# local index loss. This is intentionally not a benchmark on the busy host.
tmp = folder/'cache-loss'
tmp.mkdir()
p = sample_project(tmp)
for i in range(4):
    finished_ticket(p, tmp, title=f'Completed {i}')
create_investigation(p, tmp, title='Current planned work')
eng = Engine.discover(p.root)
original_walk = History.walk
counts = {'calls': 0, 'entries': 0}
def walking(self, *args, **kw):
    counts['calls'] += 1
    for item in original_walk(self, *args, **kw):
        counts['entries'] += 1
        yield item
History.walk = walking
for method in ('resume', 'status', 'harness_status'):
    shutil.rmtree(p.root/'.aew/local', ignore_errors=True)
    counts.update(calls=0, entries=0)
    try:
        out = getattr(Engine.discover(p.root), method)()
        emit('cache_loss_'+method, history=dict(counts), returned_keys=sorted(out),
             cold_count=load_control(p.root)['cold']['root']['count'])
    except Exception as exc:
        emit('cache_loss_'+method, history=dict(counts), error=type(exc).__name__, message=str(exc))
History.walk = original_walk
assert_control_invariants(p)

# Full-audit transitive closure: a genuinely integrated, migrated Ticket has
# verification records referring to engine-produced check evidence and its logs.
t = CP.Template(folder/'check-closure'/'repo')
completed = t.planned('Real integrated ticket')
t.done(completed)
eng = Engine.discover(t.root)
eng.migrate(token=t.token, expect_rev=t.rev())
bundle = load_yaml((t.root/'.aew/work'/completed/'archive.yaml').read_text(encoding='utf-8'))
pins = {r['id'] for r in bundle['unit'].get('evidence', [])}
from aew.knowledge import evidence as E
records, errors = E.scan(t.root/'.aew', completed)
checks = [e for e in records if e['kind']=='check_result']
emit('full_audit_check_coverage', ingested_ids=sorted(pins),
     checks=[{'id':e['id'],'path':e.get('_path'), 'ingested':e['id'] in pins,
              'check':e.get('check')} for e in checks], scan_errors=errors)
if checks:
    chosen = checks[0]
    from aew.util import parse_frontmatter
    candidates = list((t.root/'.aew/evidence').rglob(chosen['id']+'.md'))
    assert len(candidates)==1, candidates
    path = candidates[0]
    before = eng.history_audit(full=True)
    path.write_bytes(path.read_bytes()+b'\nCORRUPTED ENGINE CHECK PAYLOAD\n')
    from aew.errors import AEWError
    try:
        after = Engine.discover(t.root).history_audit(full=True)
    except AEWError as exc:
        after = {'code': exc.code, 'message': exc.message, 'details': exc.details}
    emit('full_audit_check_corruption', check_id=chosen['id'], check_is_ingested=chosen['id'] in pins,
         before=before, after=after, changed_path=str(path.relative_to(t.root)))
