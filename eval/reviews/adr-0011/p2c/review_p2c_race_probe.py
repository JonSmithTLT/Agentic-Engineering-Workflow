"""Independent P2c index-contention and adversarial R2 race probes."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tests/helpers'), str(ROOT / 'tests/integration')]
from aewflow import sample_project
from test_history_surface import finished_ticket, audit
from conftest import Project, clean_env
from invariants import load_control

def emit(name, **values):
    print(json.dumps(dict(probe=name, **values)), flush=True)

def parsed(r):
    try:
        data = r.json if r.returncode == 0 else r.error
    except Exception:
        data = {'stdout': r.stdout, 'stderr': r.stderr}
    return {'returncode': r.returncode, 'result': data}

source = json.loads((ROOT / 'review-p2c-probes.jsonl').read_text().splitlines()[0])
p = Project(Path(source['fixtures']) / 'surface/repo')
index_path = p.root / '.aew/local/history.sqlite'
p.ok('history', 'list')
conn = sqlite3.connect(index_path, isolation_level=None)
conn.execute('BEGIN IMMEDIATE')
try:
    blocked = p.aew('history','reindex')
finally:
    conn.execute('ROLLBACK')
    conn.close()
released = p.aew('history','reindex')
emit('reindex_contention', blocked=parsed(blocked), released=parsed(released))

folder = Path(tempfile.mkdtemp(prefix='race-', dir=ROOT))
p = sample_project(folder)
finished_ticket(p, folder, title='Initially verified')
audit(p, '--full')
before = load_control(p.root)['cold']['verified']
gate = folder / 'hold'
gate.write_text('')
kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {'start_new_session': True}
proc = subprocess.Popen([sys.executable,'-m','aew','-C',str(p.root),'history','audit','--token',p.token,'--expect-rev',str(p.rev())], env=clean_env({'AEW_PAUSE':f'history.audit_after_verify={gate}'}), stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding='utf-8', **kwargs)
try:
    deadline = time.monotonic() + 120
    while not Path(str(gate)+'.reached').exists():
        assert proc.poll() is None and time.monotonic() < deadline
        time.sleep(0.05)
    moved, _, _ = finished_ticket(p, folder, title='New entry damaged inside R2 window')
    p.lead('checkpoint')
    bundle = p.root / '.aew/work' / moved / 'archive.yaml'
    original = bundle.read_bytes()
    bundle.write_bytes(original + b'\n# damaged after append, before audit retry\n')
finally:
    gate.unlink(missing_ok=True)
stdout, stderr = proc.communicate(timeout=180)
try:
    response = json.loads(stderr if proc.returncode else stdout)
except ValueError:
    response = {'stdout':stdout,'stderr':stderr}
cold = load_control(p.root)['cold']
emit('r2_new_damage', fixtures=str(folder), returncode=proc.returncode, response=response, verified_unchanged=cold['verified']==before, current_count=cold['root']['count'])
bundle.write_bytes(original)
emit('r2_repair_control', audit=audit(p, '--full'))
