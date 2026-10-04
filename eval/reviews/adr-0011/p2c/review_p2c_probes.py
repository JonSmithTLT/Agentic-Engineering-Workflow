"""Independent P2c review probes; private fixture projects and frozen source only."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
import sqlite3

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tests/helpers'), str(ROOT / 'tests/integration')]
from aewflow import sample_project, create_investigation, dispatch, complete_investigation
from test_history_surface import finished_ticket, audit
from invariants import load_control, assert_control_invariants
from aew.engine.api import Engine
from aew.history.store import History
from aew.util import load_yaml

import aew
assert Path(aew.__file__).resolve().is_relative_to(ROOT / 'src'), aew.__file__

def emit(name, **values):
    print(json.dumps(dict(probe=name, **values)), flush=True)

def result(r):
    try:
        out = r.json if r.returncode == 0 else r.error
    except Exception:
        out = {'stdout': r.stdout, 'stderr': r.stderr}
    return {'returncode': r.returncode, 'result': out}

base = Path(tempfile.mkdtemp(prefix='independent-', dir=ROOT))
emit('source', source=str(ROOT), interpreter=sys.executable, fixtures=str(base))
folder = base / 'surface'
folder.mkdir()
p = sample_project(folder)
wid, inv, evidence = finished_ticket(p, folder)
shown = p.ok('history', 'show', evidence)
target = create_investigation(p, folder, title='Follow-up')
failed_load = p.aew('history', 'load', evidence, '--into', target, '--reason', 'reuse the exact discovery record', '--token', p.token, '--expect-rev', str(p.rev()))
loaded = p.lead('history', 'load', wid, '--into', target, '--reason', 'fallback to the owning unit')
role, out = dispatch(p, target)
pack = Path(p.ok('context', 'pack', out['invocation'])['path']).read_text(encoding='utf-8')
emit('evidence_load', evidence=evidence, displayed_trust=shown['trust']['source'], load=result(failed_load), unit_load_ok=loaded['ok'], historical_section=pack.split('## Historical reference context',1)[1].split('## Guardrails',1)[0], pack_matches=p.ok('context','pack',out['invocation'])['matches_recorded'])
unit_show = p.ok('history', 'show', wid)
emit('storage_paths', unit_entry_path=unit_show['entry']['path'], links=p.ok('history','links',wid)['edges'])
p.lead('work', 'transition', target, '--to', 'CANCELLED', '--reason', 'review complete')
assert_control_invariants(p)

before_audit = audit(p, '--full')
unit = p.ok('work', 'show', wid)['control']
ref = next(e for e in unit['evidence'] if e['id'] == evidence)
path = p.root / '.aew' / ref['path']
original = path.read_bytes()
path.write_bytes(original + b'\n# independent review: changed sealed evidence\n')
advisory = p.aew('history', 'audit', '--full')
recorded = p.aew('history', 'audit', '--full', '--token', p.token, '--expect-rev', str(p.rev()))
cold = load_control(p.root)['cold']
emit('evidence_audit', prior_full_ok=before_audit['ok'], evidence_show=result(p.aew('history','show',evidence)), advisory=result(advisory), recorded=result(recorded), verified_matches_current=(cold['verified']['count']==cold['root']['count'] and cold['verified']['h']==cold['root']['head_h']))
path.write_bytes(original)
bundle = p.root / '.aew/work' / wid / 'archive.yaml'
original_bundle = bundle.read_bytes()
bundle.write_bytes(original_bundle + b'\n# independent review: changed bundle\n')
emit('bundle_audit_positive_control', full_audit=result(p.aew('history','audit','--full')))
bundle.write_bytes(original_bundle)
assert_control_invariants(p)

offer = p.lead('lead', 'handoff', 'offer')['offer']
accepted = p.ok('lead','handoff','accept','--offer',offer,'--expect-rev',str(p.rev()))
p.token = accepted['token']
lead_id = p.ok('history','list','--kind','lead')['items'][0]['id']
lead_show = p.ok('history','show',lead_id)
lead_doc = load_yaml((p.root / '.aew/history/lead/000001.yaml').read_text(encoding='utf-8'))
verifiers = [t['verifier'] for t in lead_doc['tokens'].values()]
target = create_investigation(p, folder, title='Lead historical reference')
p.lead('history','load',lead_id,'--into',target,'--reason','reference historical authority transfer')
role, out = dispatch(p, target)
pack_result = p.aew('context','show',out['invocation'])
assert pack_result.returncode == 0, pack_result.stderr
pack = pack_result.stdout
emit('lead_reference_redaction', display_redacted=all(t['verifier']=='<redacted>' for t in lead_show['record']['tokens'].values()), verifier_count=len(verifiers), verifiers_in_context_output=sum(v in pack for v in verifiers), pack_matches=p.ok('context','pack',out['invocation'])['matches_recorded'])
p.lead('work', 'transition', target, '--to', 'CANCELLED', '--reason', 'review complete')
assert_control_invariants(p)

index_path = p.root / '.aew/local/history.sqlite'
index_path.unlink(missing_ok=True)
engine = Engine.discover(p.root)
walked = []
original_walk = History.walk
def counted_walk(self, *args, **kwargs):
    for entry in original_walk(self, *args, **kwargs):
        walked.append(entry['id'])
        yield entry
with patch.object(History, 'walk', counted_walk):
    resumed = engine.resume()
emit('resume_index_rebuild', current_history_count=load_control(p.root)['cold']['root']['count'], walked_count=len(walked), walked_ids=walked, resume_work_count=len(resumed['work']))

connection = sqlite3.connect(index_path, isolation_level=None)
connection.execute('BEGIN IMMEDIATE')
try:
    blocked = p.aew('history','reindex')
finally:
    connection.execute('ROLLBACK')
    connection.close()
released = p.aew('history','reindex')
emit('reindex_contention', blocked=result(blocked), released=result(released))
