"""Proof-only scheduling barriers for the original broker integration test."""

import os
import threading
import time

import pytest


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    from fake_harness import HarnessLab

    from aew.harness import steering_loop, wake_queue
    from aew.surface import availability

    stage_chosen = threading.Event()
    assignment_observed = threading.Event()
    base = os.environ['PROOF_CASE'] == 'base'
    release = item.funcargs['tmp_path'] / 'release-progress-worker'
    real_script = HarnessLab.script
    real_lead = HarnessLab.lead
    real_guard = availability.stage_availability
    real_tick = wake_queue.WakeQueue.tick
    real_activate = steering_loop.SteeringLoop.activate

    def script(lab, name, steps):
        # The fake worker waits at a tool boundary, preserving the original write and hang steps.
        return real_script(lab, name, {**steps, 'steps': [{'do': 'wait_file', 'path': str(release)}, *steps['steps']]})

    def lead(lab, *args, **kwargs):
        if args[:2] == ('work', 'assign'):
            assert stage_chosen.wait(30), 'broker never chose ticket_start'
        return real_lead(lab, *args, **kwargs)

    def guard(engine, stage, args):
        if stage == 'ticket_start' and threading.current_thread().name == 'aew-steering-loop':
            stage_chosen.set()
            deadline = time.monotonic() + 30
            while engine.store.current()['work'][args['work_id']]['state'] != 'ASSIGNED':
                assert time.monotonic() < deadline, 'assignment did not become visible'
                time.sleep(0.02)
            assignment_observed.set()
        return real_guard(engine, stage, args)

    def activate(loop):
        stop = real_activate(loop)
        if assignment_observed.is_set() and not base and not release.exists():
            print('fresh projection result:', stop.code, flush=True)
            if stop.code == steering_loop.IDLE:
                release.touch()
        return stop

    def tick(queue):
        real_tick(queue)
        posted = queue.doc.get('last_posted') or {}
        if base and assignment_observed.is_set() and 'loop_waiting' in posted.get('why', ()) and not release.exists():
            print('original race posted loop_waiting before the worker write', flush=True)
            release.touch()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(HarnessLab, 'script', script)
        patch.setattr(HarnessLab, 'lead', lead)
        patch.setattr(availability, 'stage_availability', guard)
        patch.setattr(steering_loop.SteeringLoop, 'activate', activate)
        patch.setattr(wake_queue.WakeQueue, 'tick', tick)
        try:
            return (yield)
        finally:
            try:
                assert assignment_observed.is_set() and release.exists(), 'scheduling plant did not run'
            finally:
                release.touch()
