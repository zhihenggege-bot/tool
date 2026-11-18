"""Continue user-authorized simulated-input tests; defer ventilation until last."""
from v1055_bench_context_20261109 import *
from continuous_followups_v1055_20261109 import paused
import subprocess,sys


def latest_restore():
    paths=list(D.glob('remaining571_heat_dynamic_*.json'))
    p=max(paths,key=lambda v:v.stat().st_mtime)
    d=json.loads(p.read_text('utf8'))
    assert d.get('restored') is True and not d.get('cleanup_error') and not d.get('restore_mismatches'),('predecessor recovery not confirmed',p)
    return p


def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dep=a.after.resolve();journal=D/('manual_scope_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),dependency=dep.relative_to(R).as_posix(),status='waiting_without_hardware',actions=[],
        user_instruction='Use manual simulation first; postpone ventilation until other tests finished')
    dump(journal,q)
    while True:
        paused()
        try:previous=json.loads(dep.read_text('utf8'))
        except (OSError,ValueError):previous={}
        if previous.get('finished'):break
        time.sleep(3)
    latest_restore();q.update(status='running',started_test=now());dump(journal,q)
    from remaining_sensor_latches_v1055_20261109 import run as sensors
    from remaining_eev_live_20261106 import main as eev
    actions=[('sensor-latches-cooling',lambda:sensors(0)),
             ('sensor-latches-heating',lambda:sensors(1)),
             ('EEV-startup-history-cap',lambda:eev(startups=True))]
    try:
        for name,fn in actions:
            paused();latest_restore();row=dict(name=name,status='running',started=now());q['actions'].append(row);dump(journal,q)
            try:fn();row['status']='finished_see_per_case_scope'
            except Exception:
                row.update(status='failed_or_unavailable',error=traceback.format_exc());dump(journal,q)
                latest_restore()
            row['finished']=now();dump(journal,q)
        for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py'):
            proc=subprocess.run([sys.executable,'-u',script],cwd=R,capture_output=True,text=True,encoding='utf8',timeout=300)
            q['actions'].append(dict(script=script,returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr));dump(journal,q)
        q['status']='completed'
    finally:q['finished']=now();dump(journal,q)
    print('MANUAL SCOPE BATCH FINISHED',journal,flush=True)


if __name__=='__main__':main()
