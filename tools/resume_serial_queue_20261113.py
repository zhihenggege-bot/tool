"""Resume the interrupted final batch after independently verified recovery."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R = Path(__file__).resolve().parents[1]
D = R / '测试证据/逐项测试_20261113'

def save(p, data):
    temp = p.with_suffix('.resume.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
    temp.replace(p)

def main():
    path = D / 'controller.json'
    q = json.loads(path.read_text('utf8'))
    assert q['status'] in ('restoration_or_controller_error', 'scope_changed_ready_to_resume')
    assert len(q['executed']) == 27
    recovery = sorted(D.glob('after_serial_interruption_recovery_*.json'))[-1]
    assert json.loads(recovery.read_text('utf8')).get('verified')
    backup = D / ('controller_before_serial_resume_' + time.strftime('%H%M%S') + '.json')
    backup.write_text(path.read_text('utf8'), encoding='utf8')
    q.setdefault('interruptions', []).append(dict(error=q.pop('error', None), recovery=recovery.name, prior_pid=q['pid']))
    q.update(pid=os.getpid(), status='running')
    save(path, q)

    def call(key, args, script='tools/full_queue_dispatch_20261113.py'):
        row = dict(key=key, args=args, started=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
        q['steps'].append(row)
        out = D / f'step_{len(q["steps"]):03d}_{key}.log'
        with out.open('w', encoding='utf8') as stream:
            child = subprocess.Popen([sys.executable, '-X', 'utf8', '-u', script, *args], cwd=R, stdout=stream, stderr=subprocess.STDOUT)
            row.update(pid=child.pid, output=str(out.relative_to(R)))
            q['active'] = row
            save(path, q)
            rc = child.wait()
        row.update(exitcode=rc, finished=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
        q.pop('active', None)
        save(path, q)
        return rc

    try:
        assert call('serial_recovery_independent_audit', ['audit']) == 0
        if (R / '.codex-tmp/continuous_v1055_pause.request').exists():
            q['status'] = 'paused_by_user'
            return
        task = q['tasks'][-1]
        rc = call(task['key'] + '_resumed', task['arguments'])
        assert any(call('serial_recheck_restoration_' + str(n), ['audit']) == 0 for n in range(3)), 'Restoration not verified'
        q['executed'].append(dict(key=task['key'], exitcode=rc, verdict='Review actual case journal, not exit status'))
        q['status'] = 'production_queue_running'
        save(path, q)
        if (R / '.codex-tmp/continuous_v1055_pause.request').exists():
            q['status'] = 'paused_by_user'
            return
        q['formal_controller_exitcode'] = call('formal_28_rows', [], 'tools/production_queue_controller_20261113.py')
        assert (D / 'production_activated.json').exists()
        assert call('pre_soak_formal_audit', ['audit'], 'tools/production_queue_dispatch_20261113.py') == 0
        if (R / '.codex-tmp/continuous_v1055_pause.request').exists():
            q['status'] = 'paused_by_user'
            return
        q['stability_exitcode'] = call('current_firmware_uninterrupted2h', ['soak'], 'tools/production_queue_dispatch_20261113.py')
        assert call('final_production_readback', ['final-audit'], 'tools/production_queue_dispatch_20261113.py') == 0
        q['status'] = 'all_scheduled_batches_executed_review_case_verdicts'
    except BaseException as exc:
        q.update(status='restoration_or_controller_error', error=repr(exc))
        raise
    finally:
        q['updated'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        save(path, q)

if __name__ == '__main__':
    main()
