"""Check the changed perf cloner on one genuinely cloned completed Ticket."""
import json
import sys
import tempfile
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tools/perf'))
import aew
import control_plane as CP
from aew.engine.api import Engine
assert Path(aew.__file__).resolve().is_relative_to(root/'src')
assert Path(sys.executable).resolve().is_relative_to(root/'.venv')
folder=Path(tempfile.mkdtemp(prefix='review-cloner-control-',dir=root))
t=CP.make_template(folder/'repo')
before=len(t.eng.store.read()['work'])
CP.add_units(t.root,done=1,planned=0)
after=len(t.eng.store.read()['work'])
assert after==before+1
migration=Engine.discover(t.root).migrate(token=t.token,expect_rev=t.rev())
audit=Engine.discover(t.root).history_audit(full=True)
assert migration['archived']['units']==2 and audit['ok']
print(json.dumps({'probe':'perf_clone_integrity','fixtures':str(folder),'before_units':before,'after_units':after,'migration':migration,'audit':audit}),flush=True)
