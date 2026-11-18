"""Today's sequential controller: preserve failed evidence, audit before next case."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/逐项测试_20261113'
PAUSE=R/'.codex-tmp/continuous_v1055_pause.request'
DISPATCH='tools/full_queue_dispatch_20261113.py'
def now():return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def dump(p,q):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');t.replace(p)

def plan():
    rows=[dict(key='R02_reverse_ambient_probe_isolation',arguments=['isolation','2']),
          dict(key='R04_all_outdoor_environment_summary',arguments=['ambient-summary'])]
    for kind in ('fault-both','fan-fault','disable-both','lp-defrost'):
        rows.append(dict(key='regression_defrost_'+kind,arguments=['legacy','tools/bench_remaining_defrost_matrix_20261111.py',kind]))
    rows.extend([dict(key='Q01_Q02_type1_ambient_boundaries',arguments=['ambient-history-gaps','--value','1']),
                 dict(key='Q03_analog_HP_threshold',arguments=['legacy','tools/bench_remaining_adc_20261111.py','pressure']),
                 dict(key='Q04_indoor_AI',arguments=['legacy','tools/bench_remaining_adc_20261111.py','ventilation']),
                 dict(key='Q05_manual_protection',arguments=['legacy','tools/bench_remaining_adapter_20261111.py','manual-contacts']),
                 dict(key='Q06_single_vfd_curve',arguments=['vfd-curve','--value','12']),
                 dict(key='Q07_DA8',arguments=['legacy','tools/bench_remaining_da8_20261111.py'])])
    old=json.loads((R/'测试证据/剩余全队列_20261112/controller.json').read_text('utf8'))
    pending=[row for row in old['tasks'] if row['key'] not in {x['key'] for x in old['executed']}]
    assert len(pending)==17
    rows.extend(row for row in pending if row['arguments']!=['soak'])
    return rows

def main():
    path=D/'controller.json';assert not path.exists(),'Resume journal explicitly; never overwrite'
    q=dict(started=now(),pid=os.getpid(),status='running',versions='330 V10.61 /316 V12.43',profile='BENCH_ONLY_3S',
           authorization='接着测试！认真烧录测试！',tasks=plan(),steps=[],executed=[],
           unexecuted_later=['28 formal timing rows on reviewed current PRODUCTION image','uninterrupted2h after formal queue','83 constrained rows review'],
           scope='Exit status is execution only; per-case evidence determines verdict')
    dump(path,q)
    def call(key,args,script=DISPATCH):
        row=dict(key=key,args=args,started=now());q['steps'].append(row)
        p=D/f'step_{len(q["steps"]):03d}_{key}.log'
        with p.open('w',encoding='utf8') as f:
            child=subprocess.Popen([sys.executable,'-X','utf8','-u',script,*args],cwd=R,stdout=f,stderr=subprocess.STDOUT)
            row.update(pid=child.pid,output=str(p.relative_to(R)));q['active']=row;dump(path,q)
            print('QUEUE START',key,flush=True)
            result=child.wait()
        row.update(exitcode=result,finished=now());q.pop('active',None);dump(path,q)
        print('QUEUE END',key,result,flush=True);return result
    def audit():
        for n in range(3):
            if call('independent_restoration_audit_'+str(n),['audit'])==0:return
        raise RuntimeError('Restoration not verified; investigate before next hardware stimulus')
    try:
        audit()
        for row in q['tasks']:
            if PAUSE.exists():q['status']='paused_by_user';break
            result=call(row['key'],row['arguments'])
            audit()
            q['executed'].append(dict(key=row['key'],exitcode=result,verdict='Review actual case journal, not exit status'))
            dump(path,q)
        if q['status']=='running':
            q['status']='production_queue_running';dump(path,q)
            formal=call('formal_28_rows',[],'tools/production_queue_controller_20261113.py')
            q['formal_controller_exitcode']=formal
            assert (D/'production_activated.json').exists(),'Production deployment not verified; inspect before further hardware actions'
            assert call('before_soak_production_restoration',['audit'],'tools/production_queue_dispatch_20261113.py')==0
            if PAUSE.exists():q['status']='paused_by_user'
            else:
                soak=call('current_firmware_uninterrupted2h',['soak'],'tools/production_queue_dispatch_20261113.py')
                q['stability_exitcode']=soak
                assert call('final_production_readback',['final-audit'],'tools/production_queue_dispatch_20261113.py')==0
                q['status']='all_scheduled_batches_executed_review_case_verdicts'
    except BaseException as exc:q.update(status='restoration_or_controller_error',error=repr(exc));raise
    finally:q['updated']=now();dump(path,q)

if __name__=='__main__':main()
