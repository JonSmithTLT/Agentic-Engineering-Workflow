"""Verify the original native archives from the full #524 and #552 Windows fixture proofs."""

import ast
import json
import sys
from collections import Counter
from pathlib import Path

suites = {'tests/integration/test_history_store.py', 'tests/regression/test_log_sealing_model.py'}
seed = json.loads(Path('tests/durations.json').read_text())['platforms']['win32']
all_nodes = {node for node in seed if node.partition('::')[0] in suites}
always = set()
for suite in suites:
    for declaration in ast.parse(Path(suite).read_text(encoding='utf-8')).body:
        if isinstance(declaration, ast.FunctionDef) and any(ast.unparse(d) == 'pytest.mark.exploratory'
                                                            for d in declaration.decorator_list):
            always.update(n for n in all_nodes if n.split('::')[-1].partition('[')[0] == declaration.name)
expected = all_nodes - always
assert len(all_nodes) == 78 and len(always) == 1 and len(expected) == 77
for case in ('ordinary', 'override', 'failure', 'control'):
    actual = set()
    events = Counter()
    files = list((Path(sys.argv[1]) / f'windows-fixture-{case}').glob('*.json'))
    assert files, f'missing native files for {case}'
    for file in files:
        data = json.loads(file.read_text())
        actual.update(data['nodes'])
        for row in data['counts']:
            events[row['phase'], row['target']] += row['count']
    if case in ('ordinary', 'override'):
        assert actual == expected, (sorted(expected - actual), sorted(actual - expected))
        assert set(events) == {('collection', 'process:git'), ('collection', 'process:python.exe'),
                               ('finish', 'process:git')}, events
    elif case == 'control':
        assert len(actual) == 1 and all(events[pair] > 0 for pair in (
            ('setup', 'registry'), ('call', 'child-dispatch'), ('teardown', 'doctor')))
    else:
        assert len(actual) == 1 and actual.pop().endswith('::test_fixture_failure_path')
    print(f'{case}: {len(expected) if case in ("ordinary", "override") else 1} node(s); {sorted(events.items())}')
