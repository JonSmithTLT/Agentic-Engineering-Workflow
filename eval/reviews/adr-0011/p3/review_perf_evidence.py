"""Recompute supplied evidence only: no timed workloads or project generation."""
import contextlib
import importlib.util
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gate', ROOT/'tools/perf/adr0011_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
DATA = ROOT/'eval/adr-0011/perf'
required_ops = set(gate.BOUNDS)
summary = []
for label, flatname, hiername, abname in (
    ('windows','p3-windows.json','p3-hierarchy-windows.json','p3-windows-h2-ab.json'),
    ('wsl','p3-linux.json','p3-hierarchy-linux.json',None),
    ('rocky8-userland-wsl','p3-rocky8-flat.json','p3-rocky8-hierarchy.json',None),
):
    flat = json.loads((DATA/flatname).read_text())
    hierarchy = json.loads((DATA/hiername).read_text())
    for series, expected in ((flat, [(20,250),(20,1000),(20,3000),(200,250),(500,250),(1000,250)]),
                             (hierarchy, [(5,250),(5,1000),(5,3000)])):
        for o,c in expected:
            point = next(r for r in series if r['point']=={'open':o,'completed':c})
            assert required_ops <= {v['op'] for v in point['ops']}, (label,o,c)
    args = [str(ROOT/'tools/perf/adr0011_gate.py'),str(DATA/flatname),'--hierarchy',str(DATA/hiername)]
    if abname:
        args += ['--ab',str(DATA/abname)]
        paired=json.loads((DATA/abname).read_text())
        assert required_ops <= set(paired['ops'])
        deltas=[]
        for op, value in paired['ops'].items():
            a,b=value['samples_s']
            assert len(a)==len(b)==paired['rounds']==6
            ma,mb=statistics.median(a),statistics.median(b)
            delta=statistics.median(y-x for x,y in zip(a,b))
            assert abs(ma-value['median_s'][0]) < 0.00011
            assert abs(mb-value['median_s'][1]) < 0.00011
            assert abs(delta-value['paired_delta_s'][0]) < 0.00011
            if not op.startswith('CLI floor'):
                deltas.append(delta)
        max_flat_delta=max(deltas)
    else:
        a,b=[next(r for r in flat if r['point']=={'open':20,'completed':c}) for c in (250,3000)]
        small={v['op']:v for v in a['ops']}
        max_flat_delta=max(v['wall_s']-small[v['op']]['wall_s'] for v in b['ops'] if v['op'] in required_ops)
    sys.argv=args
    with (ROOT/f'review-perf-{label}.md').open('w',encoding='utf-8') as output:
        with contextlib.redirect_stdout(output):
            code=gate.main()
    assert code==0, label
    for series,open_,kind in ((flat,20,'flat'),(hierarchy,5,'hierarchy')):
        a,b=[next(r for r in series if r['point']=={'open':open_,'completed':c}) for c in (250,3000)]
        aa,bb=[{v['op']:v for v in r['ops']} for r in (a,b)]
        ratio=b['footprint']['control_bytes']/a['footprint']['control_bytes']
        share=b['footprint']['history_bytes']['total']/b['footprint']['control_bytes']
        resume_equal={k:v for k,v in aa['resume']['counts'].items() if k!='parse_bytes'} == \
                     {k:v for k,v in bb['resume']['counts'].items() if k!='parse_bytes'}
        delta=max_flat_delta if kind=='flat' else max(bb[o]['wall_s']-aa[o]['wall_s'] for o in required_ops)
        assert ratio<=1.25 and share<=.20 and delta<=.25 and b['micro']['control_reparse_s']<=.25 and resume_equal
        assert all(bb[o]['wall_s']<=bound for o,bound in gate.BOUNDS.items())
        summary.append(dict(platform=label,series=kind,gate_exit=code,hot_growth=ratio,history_share=share,
                            max_H2_delta_s=delta,reparse_ms=b['micro']['control_reparse_s']*1000,
                            resume_counters_equal=resume_equal))
(ROOT/'review-perf-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
