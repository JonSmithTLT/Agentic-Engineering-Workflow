"""Continue audit probes on the genuine integrated fixture built by review_p3_probes.py."""
import json
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
import aew
assert Path(aew.__file__).resolve().is_relative_to(ROOT/'src')
if sys.platform=='win32':
    original=subprocess.Popen
    def hidden(*args,**kw):
        kw['creationflags']=kw.get('creationflags',0)|subprocess.CREATE_NO_WINDOW
        return original(*args,**kw)
    subprocess.Popen=hidden
from aew.engine.api import Engine
from aew.errors import AEWError
from aew.knowledge import evidence as E
from aew.util import load_yaml, parse_frontmatter, sha256_file
fixture=Path(json.loads((ROOT/'review-p3-probes.jsonl').read_text().splitlines()[0])['fixtures'])
repo=fixture/'check-closure/repo'
eng=Engine.discover(repo)
suffix=b'\nCORRUPTED ENGINE CHECK PAYLOAD\n'
for path in (repo/'.aew/evidence/T-0001').glob('*.md'):
    raw=path.read_bytes()
    if raw.endswith(suffix):
        path.write_bytes(raw[:-len(suffix)])

def result(method,*args,**kwargs):
    try:
        return {'ok':True,'result':getattr(Engine.discover(repo),method)(*args,**kwargs)}
    except AEWError as exc:
        return {'ok':False,'code':exc.code,'message':exc.message,'details':exc.details}
def emit(name,**kw):
    print(json.dumps(dict(probe=name,**kw)),flush=True)
bundle=load_yaml((repo/'.aew/work/T-0001/archive.yaml').read_text())
pinids={e['id'] for e in bundle['unit']['evidence']}
records,_=E.scan(repo/'.aew','T-0001')
checks=[e for e in records if e['kind']=='check_result']
verification_checks=sorted({c for e in records if e['kind']=='verification'
                            for claim in e['verification']['claims'] for c in claim.get('checks',[])})
emit('audit_baseline',audit=result('history_audit',full=True),verification_checks=verification_checks)
for record in (checks[0], next(e for e in checks if e['id'] not in pinids and e['id'] in verification_checks)):
    path=repo/'.aew'/record['_path']
    raw=path.read_bytes()
    path.write_bytes(raw+suffix)
    emit('audit_check_payload',id=record['id'],directly_ingested=record['id'] in pinids,
         referenced_by_verification=record['id'] in verification_checks,
         audit=result('history_audit',full=True),history_show=result('history_show',record['id']),
         independent_scan_problems=E.scan(repo/'.aew','T-0001')[1])
    path.write_bytes(raw)
record=checks[0]
logref=record['evidence'][0]
path=repo/'.aew'/logref['path']
raw=path.read_bytes()
assert sha256_file(path)==logref['sha256']
path.write_bytes(raw+b'\nCORRUPTED PINNED LOG\n')
emit('audit_transitive_log',id=record['id'],directly_ingested=record['id'] in pinids,
     log_path=logref['path'],pinned_hash=logref['sha256'],changed_hash=sha256_file(path),
     audit=result('history_audit',full=True))
path.unlink()
emit('audit_missing_transitive_log',log_path=logref['path'],audit=result('history_audit',full=True))
path.write_bytes(raw)
