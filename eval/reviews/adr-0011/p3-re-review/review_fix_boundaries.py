"""Local upgrade and archival integrity checks using disposable projects only."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path[:0]=[str(root/'tools/perf')]
import aew
import control_plane as CP
from aew.engine.api import Engine
from aew.errors import AEWError
from aew.knowledge import evidence as E
from aew.util import load_yaml,sha256_file
assert Path(aew.__file__).resolve().is_relative_to(root/'src')
assert Path(sys.executable).resolve().is_relative_to(root/'.venv')
folder=Path(tempfile.mkdtemp(prefix='review-fix-boundaries-',dir=root))
def emit(probe,**kw):
 print(json.dumps(dict(probe=probe,**kw)),flush=True)
def call(repo,method,**kw):
 try:
  return {'ok':True,'result':getattr(Engine.discover(repo),method)(**kw)}
 except AEWError as e:
  return {'ok':False,'code':e.code,'message':e.message,'details':e.details}
emit('environment',source=aew.__file__,interpreter=sys.executable,fixtures=str(folder))
# A cited engine check is changed after completion, before the v1 migration snapshots it.
t=CP.make_template(folder/'changed-before-migration')
path=t.root/'.aew/evidence/T-0001/INV-0003-check-unit-4.md'
saved=path.read_bytes()
path.write_bytes(saved+b'\nChanged after completion, before archival.\n')
scan=E.scan(t.root/'.aew','T-0001')[1]
out=call(t.root,'migrate',token=t.token,expect_rev=t.rev())
audit=call(t.root,'history_audit',full=True) if out['ok'] else None
emit('changed_cited_check_before_migration',scan_problems=scan,migration=out,audit=audit)
if out['ok']:
 bundle=load_yaml((t.root/'.aew/work/T-0001/archive.yaml').read_text(encoding='utf-8'))
 emit('changed_cited_check_pin',pins=bundle.get('cited_evidence'),actual_hash=sha256_file(path))
path.write_bytes(saved)
# Re-check an existing pre-fix v2 project. Copy it first; no operation writes to the previous review.
old=root.parent/'ADR-0011-P3-c6caa4c-42932b'
fixture=Path(json.loads((old/'review-p3-probes.jsonl').read_text(encoding='utf-8').splitlines()[0])['fixtures'])
repo=folder/'pre-fix-v2'
shutil.copytree(fixture/'check-closure/repo',repo,symlinks=True)
bundle=load_yaml((repo/'.aew/work/T-0001/archive.yaml').read_text(encoding='utf-8'))
control=sha256_file(repo/'.aew/state/control.yaml')
emit('pre_fix_v2_baseline',cited_evidence=bundle.get('cited_evidence'),audit=call(repo,'history_audit',full=True))
path=repo/'.aew/evidence/T-0001/INV-0003-check-unit-4.md'
saved=path.read_bytes()
path.write_bytes(saved+b'\nChanged existing historical cited check.\n')
emit('pre_fix_v2_changed_cited_check',audit=call(repo,'history_audit',full=True),
     scan_problems=E.scan(repo/'.aew','T-0001')[1],control_unchanged=control==sha256_file(repo/'.aew/state/control.yaml'))
path.write_bytes(saved)
# Positive control for the repaired perf cloner: renamed logs still match their record pins.
t=CP.make_template(folder/'cloned-evidence')
CP.add_units(t.root,done=1,planned=0)
migration=call(t.root,'migrate',token=t.token,expect_rev=t.rev())
emit('perf_clone_integrity',migration=migration,audit=call(t.root,'history_audit',full=True) if migration['ok'] else None)
