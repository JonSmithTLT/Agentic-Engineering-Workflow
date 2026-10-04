"""Migration's bounded recent view when creation order differs from completion order."""
import json
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tests/helpers'),str(ROOT/'tests/integration'),str(ROOT/'tools/perf')]
import control_plane as CP
from aewflow import DISCOVERY
from test_migration import migrate
from invariants import load_control,assert_control_invariants
from aew.engine.api import Engine

folder=Path(tempfile.mkdtemp(prefix='recent-',dir=ROOT))
t=CP.Template(folder/'repo')
ids=[t.planned(f'Investigation {n}',mutating=False) for n in range(1,22)]
completion_order=[]
for wid in reversed(ids):
    out=t.lead('work_dispatch',work_id=wid)
    t.lead('work_transition',work_id=wid,to='RUNNING')
    ev=t.eng.submit(invocation_token=out['invocation_token'],kind='discovery_record',text=CP.submission(DISCOVERY))['evidence']
    t.lead('evidence_ingest',work_id=wid,evidence_id=ev)
    t.lead('work_accept',work_id=wid)
    completion_order.append(wid)
before=load_control(t.root)
assert_control_invariants(t)
last=completion_order[-1]
earliest=completion_order[0]
out=migrate(t)
assert out.returncode==0,out.stderr
state=load_control(t.root)
eng=Engine.discover(t.root)
resumed=[w['id'] for w in eng.resume()['work']]
listed=[w['id'] for w in eng.work_list()['items']]
assert_control_invariants(t)
print(json.dumps({'probe':'recent_after_migration','fixtures':str(folder),'completion_order':completion_order,
    'most_recent':{'id':last,'at':before['work'][last]['history'][-1]['at']},
    'oldest':{'id':earliest,'at':before['work'][earliest]['history'][-1]['at']},
    'recent_ids':[w['id'] for w in state['recent']],
    'most_recent_in_resume':last in resumed,'most_recent_in_list':last in listed,
    'oldest_in_resume':earliest in resumed,'migration_ok':out.json['migrated']}),flush=True)
