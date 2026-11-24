"""Summarize monitored endpoints without printing fixture arguments."""

import json
import os
from collections import Counter
from pathlib import Path

root = Path(os.environ['RUNNER_TEMP']) / 'fixture-proof'
counts = Counter()
nodes = set()
for path in root.glob('*.json'):
    report = json.loads(path.read_text())
    nodes.update(report['nodes'])
    for record in report['counts']:
        counts[record['phase'], record['target']] += record['count']
case = os.environ['PROBE_CASE']
print(case, len(nodes), sorted(counts.items()))
if case == 'control':
    assert len(nodes) == 1
    assert counts['setup', 'registry'] and counts['call', 'child-dispatch'] and counts['teardown', 'doctor']
elif case == 'failure':
    assert len(nodes) == 1
else:
    assert len(nodes) >= 78
