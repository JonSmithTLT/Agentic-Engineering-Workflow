"""Independent P2d mixed-hierarchy migration, late parent ingest and fingerprint controls."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'tests/helpers'),str(ROOT/'tests/integration'),str(ROOT/'tools/perf')]
import control_plane as CP
from aewflow import DISCOVERY
from test_migration import migrate, parent_review, parent_verification, comparable, full
from invariants import assert_control_invariants, load_control
from conftest import make_git_repo, git
from aew.engine.api import Engine
from aew.snapshot import fingerprint as F

def emit(name,**values): print(json.dumps(dict(probe=name,**values)),flush=True)
folder=Path(tempfile.mkdtemp(prefix='composition-',dir=ROOT))
emit('source',fixtures=str(folder))
t=CP.Template(folder/'mixed'/'repo')
epic=t.parent_unit('epic','Open initiative',None)
closed=t.parent_unit('story','Finished objective',epic)
open_story=t.parent_unit('story','Pending objective',epic)

def finished(parent,title):
    wid=t.planned(title,mutating=False,parent=parent)
    dispatch=t.lead('work_dispatch',work_id=wid)
    t.lead('work_transition',work_id=wid,to='RUNNING')
    ev=t.eng.submit(invocation_token=dispatch['invocation_token'],kind='discovery_record',text=CP.submission(DISCOVERY))['evidence']
    t.lead('evidence_ingest',work_id=wid,evidence_id=ev)
    t.lead('work_accept',work_id=wid)
    return wid

finished(closed,'Accepted investigation')
cancelled=t.planned('Cancelled investigation',mutating=False,parent=closed)
t.lead('work_transition',work_id=cancelled,to='CANCELLED',reason='no longer needed')
t.lead('review_ingest',work_id=closed,evidence_id=parent_review(t,closed))
t.lead('verify_ingest',work_id=closed,evidence_id=parent_verification(t,closed))
t.lead('work_close',work_id=closed,reason='acceptance gates passed')
finished(open_story,'Earlier accepted research')
pending_review=parent_review(t,open_story)
before=load_control(t.root)
parent_inv=next(i for i,v in before['invocations'].items() if v['work_unit']==open_story and v['role']=='reviewer')
before_pack=t.eng.context_pack(parent_inv)['matches_recorded']
assert_control_invariants(t)
out=migrate(t)
assert out.returncode==0,out.stderr
after=load_control(t.root)
eng=Engine.discover(t.root)
after_pack=eng.context_pack(parent_inv)['matches_recorded']
equal=comparable(full(t))==comparable(before)
late_ingest=eng.review_ingest(token=t.token,expect_rev=eng.store.read()['revision'],work_id=open_story,evidence_id=pending_review)
audit=eng.history_audit(full=True)
assert_control_invariants(t)
emit('mixed_hierarchy',migration=out.json,full_state_preserved=equal,
     archived_counts=after['cold']['archived'],epic_summary=after['work'][epic]['archived_children'],
     parent_pack_match_before=before_pack,parent_pack_match_after=after_pack,
     late_parent_ingest_ok=late_ingest['ok'],full_audit_ok=audit['ok'])

spec=importlib.util.spec_from_file_location('review_base_fingerprint',ROOT/'base/src/aew/snapshot/fingerprint.py')
old=importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
repo=make_git_repo(folder/'fingerprint'/'repo',{'source.py':'x=1\n','.gitignore':'*.log\n','.aew/state/control.yaml':'revision: 1\n'})
index=repo/'.git/index'
controls=[]
def compare(label,**kw):
    original=index.read_bytes()
    current=F.relevant_inputs_fingerprint(repo,**kw)
    previous=old.relevant_inputs_fingerprint(repo,**kw)
    controls.append({'case':label,'same_tree':current==previous,'real_index_unchanged':index.read_bytes()==original})
compare('clean tracked AEW')
(repo/'source.py').write_text('x=2\n',encoding='utf-8')
(repo/'new.py').write_text('y=3\n',encoding='utf-8')
(repo/'.aew/state/control.yaml').write_text('revision: 2\n',encoding='utf-8')
(repo/'.aew/untracked').write_text('history\n',encoding='utf-8')
compare('dirty source, tracked and untracked AEW')
(repo/'build.log').write_text('version=1\n',encoding='utf-8')
compare('declared ignored input',include_ignored=['build.log'])
compare('source policy exclusion',exclude=['source.py'])
git('add','source.py',cwd=repo)
(repo/'source.py').write_text('x=1\n',encoding='utf-8')
compare('staged-only source edit')
all_tree=F.working_tree_id(repo)
(repo/'.aew/untracked').write_text('changed history\n',encoding='utf-8')
emit('fingerprint_equivalence',cases=controls,working_tree_id_still_reads_aew=all_tree!=F.working_tree_id(repo))
