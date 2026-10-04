"""Independent P2d probes in disposable v1 projects; no implementation edits."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT/'tests'),str(ROOT/'tests/helpers'),str(ROOT/'tests/integration'),str(ROOT/'tools/perf')]
import aew as package
assert Path(package.__file__).resolve().is_relative_to(ROOT/'src')
import control_plane as CP
from test_migration import aew, migrate, read
from invariants import load_control, assert_control_invariants
from aew.engine.api import Engine

def emit(name, **values):
    print(json.dumps(dict(probe=name, **values)),flush=True)

def result(r):
    return {'returncode':r.returncode,'result':r.json if r.returncode==0 else r.error}

def transfer(t):
    offered=aew(t,'lead','handoff','offer','--expect-rev',str(t.rev()))
    assert offered.returncode==0, offered.stderr
    accepted=aew(t,'lead','handoff','accept','--offer',offered.json['offer'],'--expect-rev',str(t.rev()))
    assert accepted.returncode==0, accepted.stderr
    t.token=accepted.json['token']
    return accepted.json['generation']

folder=Path(tempfile.mkdtemp(prefix='independent-',dir=ROOT))
emit('source',source=str(ROOT),interpreter=sys.executable,fixtures=str(folder))
t=CP.Template(folder/'lead-retry'/'repo')
transfer(t)
crashed=migrate(t,fault='history.after_prewrite')
state=read(t)
prewritten=t.root/'.aew/history/lead/000001.yaml'
old_bytes=prewritten.read_bytes()
assert crashed.returncode==86 and state['schema']=='aew/control/v1'
gen=transfer(t)
retry=migrate(t)
assert retry.returncode==0,retry.stderr
emit('lead_handoff_after_prewrite',crash_code=crashed.returncode,schema_after_crash=state['schema'],
     generation_after_handoff=gen,orphan_unchanged=prewritten.read_bytes()==old_bytes,
     retry=result(retry),schema_after_retry=read(t)['schema'])
assert_control_invariants(t)

t=CP.Template(folder/'lead-retry-control'/'repo')
transfer(t)
crashed=migrate(t,fault='history.after_prewrite')
read(t)
retry=migrate(t)
emit('same_state_retry_control',crash_code=crashed.returncode,retry=result(retry))
assert_control_invariants(t)

t=CP.Template(folder/'empty'/'repo')
first=migrate(t)
second=migrate(t)
emit('empty_migration',first=result(first),second=result(second),hot_work=len(read(t)['work']))
assert_control_invariants(t)
