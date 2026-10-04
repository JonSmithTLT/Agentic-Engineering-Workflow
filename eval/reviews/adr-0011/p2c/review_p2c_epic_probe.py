"""Independent full-audit / Epic-closeout composition; private fixture only."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'tests/helpers'), str(ROOT / 'tests/integration')]
from aewflow import sample_project, create_unit, plan_unit, close_parent, parent_review, parent_verify
from test_history_surface import finished_ticket, audit
from invariants import load_control

folder = Path(tempfile.mkdtemp(prefix='epic-', dir=ROOT))
p = sample_project(folder)
epic = create_unit(p, 'epic', 'Full-audit composition')
plan_unit(p, folder, epic)
story = create_unit(p, 'story', 'Archived descendant', parent=epic)
plan_unit(p, folder, story)
ticket, _, rec = finished_ticket(p, folder, parent=story)
close_parent(p, story)
p.lead('review', 'ingest', epic, '--evidence', parent_review(p, epic))
p.lead('verify', 'ingest', epic, '--evidence', parent_verify(p, epic))
ref = next(e for e in p.ok('work','show',ticket)['control']['evidence'] if e['id'] == rec)
ref_path = p.root / '.aew' / ref['path']
original = ref_path.read_bytes()
p.lead('checkpoint')
ref_path.write_bytes(original + b'\n# independent review: corrupt descendant sealed evidence\n')
try:
    refused = p.aew('work','close',epic,'--reason','before audit','--token',p.token,'--expect-rev',str(p.rev()))
    initial_error = refused.error
    shown = p.aew('history','show',rec)
    audited = audit(p, '--full')
    cold = load_control(p.root)['cold']
    passed_close = p.lead('work','close',epic,'--reason','accepted full audit')
    print(json.dumps({'probe':'epic_corrupt_evidence','fixtures':str(folder),'before_audit':initial_error,
        'evidence_read':shown.error,'audit':audited,
        'verified_matches_current_before_close':cold['verified']['count']==cold['root']['count'] and cold['verified']['h']==cold['root']['head_h'],
        'close':passed_close,'epic_archived':epic not in load_control(p.root)['work']}), flush=True)
finally:
    ref_path.write_bytes(original)
