"""Resume only the 53 unexecuted batches, short first, single hardware writer."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R = Path(__file__).resolve().parents[1]
D = R / '测试证据/剩余全队列_20261112'
PAUSE = R / '.codex-tmp/continuous_v1055_pause.request'
DISPATCH = 'tools/full_queue_dispatch_20261112.py'

def now(): return time.strftime('%Y-%m-%dT%H:%M:%S%z')

def dump(path, value):
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temp.replace(path)

def estimate(key):
    # Planning estimates include setup and normal recovery, never pass criteria.
    if key == 'gateway_contention': return 60
    if key == 'indoor_DA8_observation': return 120
    if key == 'parameter_boundary_matrix': return 180
    if key == 'indoor_winter_boundaries': return 240
    if key == 'indoor_ventilation_AI': return 300
    if key.startswith('vfd_curve_'): return 360
    if key.startswith('ambient_'): return 480
    if key.startswith('heating_dispatch_'): return 540
    if key == 'analog_HP_threshold': return 600
    if key == 'manual_contact_protection': return 660
    if key == 'NTC0_peer_diagnostic_recheck': return 720
    if key == 'four_coil_continuity': return 840
    if key == 'indoor_coil_real_seconds': return 900
    if key.startswith('defrost_matrix_'): return 960
    if key.startswith('defrost_analog_'): return 1000
    if key in ('defrost_disable', 'defrost_mode', 'emergency_defrost_cleanup', 'ordinary_defrost_allocation_exclusion'): return 1100
    if key == 'two_fixed_rotation_cool': return 1200
    if key == 'all_six_fans300s': return 3600
    if key == 'two_fixed_rotation_heat': return 1800
    if key == 'current_firmware_uninterrupted2h': return 7500
    return 1500

def main():
    D.mkdir(parents=True, exist_ok=True)
    path = D / 'controller.json'
    assert not path.exists(), 'Existing queue journal must be resumed/reviewed, not overwritten'
    plan = []
    for filename in ('current_controller_085825.json', 'current_controller_093736.json'):
        source = R/'测试证据/台架执行_20261112'/filename
        old = json.loads(source.read_text('utf8'))
        for row in old['tasks']:
            if row['key'] not in old['completed']:
                plan.append(dict(**row, source=str(source.relative_to(R)), estimated_seconds=estimate(row['key'])))
    assert len(plan) == 53, len(plan)
    plan.sort(key=lambda x: x['estimated_seconds'])
    log = dict(started=now(), pid=os.getpid(), status='running',
               authorization='53批、2小时稳定性及正式时序开始执行；先短后长',
               profile='BENCH_ONLY_3S', versions='330 V10.60 /316 V12.43',
               tasks=plan, steps=[], executed=[],
               production_timing='Separate 28-row ledger; requires PRODUCTION images and adapted deadlines; BENCH cannot close these rows')
    dump(path, log)
    for marker in (PAUSE, R/'.codex-tmp/fan_minrun_spotcheck_pause.request'):
        if marker.exists():
            marker.replace(D/(marker.name+'.before_resume'))
    dump(D/'resume_authorization.json', dict(at=now(), instruction=log['authorization'],
        firmware_changes=False, order='estimated duration ascending including normal recovery',
        limits='Board input simulation and software output readback; exit code is not case acceptance'))

    def call(key, args):
        entry = dict(key=key, arguments=args, started=now())
        log['steps'].append(entry)
        target = D/(f'step_{len(log["steps"]):03d}_{key}.log')
        with target.open('w', encoding='utf8') as out:
            print('QUEUE START', key, flush=True)
            child = subprocess.Popen([sys.executable, '-X', 'utf8', '-u', DISPATCH, *args], cwd=R, stdout=out, stderr=subprocess.STDOUT)
            entry.update(pid=child.pid, output=str(target.relative_to(R)))
            log['active'] = entry
            dump(path, log)
            result = child.wait()
        entry.update(exitcode=result, finished=now())
        log.pop('active', None)
        dump(path, log)
        print('QUEUE END', key, result, flush=True)
        return result

    def audit():
        for attempt in range(3):
            if call('independent_restoration_audit_'+str(attempt), ['audit']) == 0:
                return
            time.sleep(2)
        raise RuntimeError('Restoration not verified: no further stimulus started')

    try:
        audit()
        for row in plan:
            if PAUSE.exists():
                log['status'] = 'paused_by_user'
                break
            result = call(row['key'], row['arguments'])
            audit()
            log['executed'].append(dict(key=row['key'], exitcode=result, case_verdict='Review original case evidence; not inferred from exit status'))
            dump(path, log)
        if log['status'] == 'running': log['status'] = 'bench_batches_executed_review_evidence_then_production'
    except BaseException as exc:
        log.update(status='restoration_or_controller_error', error=repr(exc))
        raise
    finally:
        log['updated'] = now()
        dump(path, log)
        print('CONTROLLER EVIDENCE', path, flush=True)

if __name__ == '__main__': main()
