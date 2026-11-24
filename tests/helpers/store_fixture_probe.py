"""Record real pytest hook and call behavior for the two candidate Windows storage test modules."""

from __future__ import annotations

import json
import os
import shlex
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    'registry': ('src/aew/harness/registry.py', 'load'),
    'doctor': ('src/aew/doctor.py', '_modules'),
    'child-dispatch': ('tests/helpers/childdiag.py', '_main'),
    'child-spawn': ('tests/helpers/childdiag.py', 'spawn'),
    'cli': ('src/aew/cli/main.py', '_main'),
    'surface': ('src/aew/surface/run.py', 'run_tool'),
}
LOOKUP = {(os.path.normcase(str(ROOT / path)), name): label for label, (path, name) in TARGETS.items()}
COUNTS = Counter()
NODES = set()
PHASE = 'collection'


def record(code, offset):
    label = LOOKUP.get((os.path.normcase(code.co_filename), code.co_name))
    if label is None and code.co_name != '<module>':
        reporters = {'check_evidence_run.py', 'evidence_problems.py',
                     'evidence_scorecard.py', 'record_cancel_evidence.py'}
        if Path(code.co_filename).name in reporters and Path(code.co_filename).parent == ROOT / 'tools/ci':
            label = 'post-run-reporter'
    if label is None:
        return sys.monitoring.DISABLE
    COUNTS[PHASE, label] += 1
    return None


def process(event, args):
    if event in {'subprocess.Popen', 'os.system', 'os.spawn', 'os.posix_spawn'}:
        # Only executable basenames are persisted. Command arguments and environment are never recorded.
        executable = None
        if event == 'subprocess.Popen':
            executable = args[0]
            if not executable and isinstance(args[1], str):
                try:
                    executable = shlex.split(args[1], posix=False)[0].strip('"')
                except (IndexError, ValueError):
                    pass
        name = Path(os.fsdecode(executable)).name.lower() if executable else 'unknown'
        # Restrict output to recognized executable kinds even when the command has unconventional quoting.
        if name not in {'git', 'git.exe', 'python', 'python.exe', 'python3', 'cmd.exe', 'powershell.exe'}:
            name = 'other'
        COUNTS[PHASE, 'process:' + name] += 1


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config, parser, args):
    monitoring = sys.monitoring
    monitoring.use_tool_id(monitoring.PROFILER_ID, 'fixture proof')
    monitoring.register_callback(monitoring.PROFILER_ID, monitoring.events.PY_START, record)
    monitoring.set_events(monitoring.PROFILER_ID, monitoring.events.PY_START)
    sys.addaudithook(process)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item):
    global PHASE
    PHASE = 'setup'
    NODES.add(item.nodeid)


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_call(item):
    global PHASE
    PHASE = 'call'


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item):
    global PHASE
    PHASE = 'teardown'


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    global PHASE
    PHASE = 'finish'


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    sys.monitoring.set_events(sys.monitoring.PROFILER_ID, 0)
    sys.monitoring.free_tool_id(sys.monitoring.PROFILER_ID)
    report = {'nodes': sorted(NODES), 'counts': [{'phase': p, 'target': t, 'count': n}
                                                 for (p, t), n in sorted(COUNTS.items())]}
    dest = Path(os.environ['FIXTURE_PROBE_OUT'])
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f'{os.getpid()}.json').write_text(json.dumps(report), encoding='utf-8')
