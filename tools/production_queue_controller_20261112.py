"""Sequential formal timing queue; invoked by the sole whole-day controller."""
from pathlib import Path
import json
import subprocess
import sys
import time
R=Path(__file__).resolve().parents[1]
D=R/'测试证据/剩余全队列_20261112/PRODUCTION'
PAUSE=R/'.codex-tmp/continuous_v1055_pause.request'
def now():return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def save(p,q):
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(p)

def plan():
    rows=[]
    for mode in (2,0,1):
        cid={0:'T14-001',1:'T14-003',2:'T14-005'}[mode]
        rows.append((f'formal_no_valves_m{mode}',['sequence','--mode',str(mode),'--ids',cid],120))
    for value,cid in ((0,'T14-011'),(1,'T14-012'),(30,'T14-013'),(90,'T14-014')):
        rows.append((f'formal_return_{value}',['sequence','--return-present','--return-delay',str(value),'--ids',cid],160+2*value))
    for value,cid in ((0,'T14-008'),(-30,'T14-007'),(30,'T14-009'),(90,'T14-010')):
        rows.append((f'formal_exhaust_{value}',['sequence','--return-present','--exhaust',str(value),'--ids',cid],160+2*abs(value)))
    for mode in (2,0,1):
        cid={0:'T14-002',1:'T14-004',2:'T14-006'}[mode]
        rows.append((f'formal_valves_m{mode}',['sequence','--mode',str(mode),'--valves','--ids',cid],300))
    rows.extend([('formal_fan15',['fan15'],600),('formal_cooling_shutdown',['loaded','--mode','0'],750),
        ('formal_cooling_humid_shutdown',['loaded','--mode','0','--humidifier'],800),
        ('formal_heating_humid_shutdown',['loaded','--mode','1','--humidifier'],850),
        ('formal_compressor_run_stop_gaps',['loaded','--mode','1'],1100),
        ('formal_ambient300',['ambient'],1350),('formal_fourway_recovery60',['fourway'],1800)])
    return sorted(rows,key=lambda row:row[2])

def main():
    D.mkdir(parents=True,exist_ok=True);p=D/'controller.json';assert not p.exists()
    q=dict(started=now(),status='running',steps=[],executed=[],tasks=plan(),
        scope='28 original rows mapped to explicit software subranges; execution never implies all acceptance clauses passed')
    save(p,q)
    def call(key,args,script='tools/production_queue_dispatch_20261112.py'):
        step=dict(key=key,args=args,started=now());q['steps'].append(step)
        out=D/(f'step_{len(q["steps"]):03d}_{key}.log')
        with out.open('w',encoding='utf8') as f:
            child=subprocess.Popen([sys.executable,'-X','utf8','-u',script,*args],cwd=R,stdout=f,stderr=subprocess.STDOUT)
            step.update(pid=child.pid,output=str(out.relative_to(R)));save(p,q)
            result=child.wait()
        step.update(exitcode=result,finished=now());save(p,q);return result
    def audit():
        for attempt in range(3):
            if call('restoration_audit_'+str(attempt),['audit'])==0:return
        raise RuntimeError('Formal restoration not verified; no next stimulus')
    try:
        assert call('deploy_PRODUCTION',[], 'tools/production_queue_deploy_20261112.py')==0,'Inspect deployment before continuation'
        audit()
        for key,args,estimated in q['tasks']:
            if PAUSE.exists():raise InterruptedError('User pause requested')
            print('FORMAL START',key,flush=True);result=call(key,args);audit()
            q['executed'].append(dict(key=key,exitcode=result,verdict='Review measured edge intervals and remaining scope'))
            save(p,q)
        assert call('T17_002_final_formal_profile_and_full_image',['final-audit'])==0,'Final formal image/profile audit incomplete'
        q['status']='formal_batches_executed_review_each_scope'
    except BaseException as exc:q.update(status='formal_controller_error',error=repr(exc));raise
    finally:q['updated']=now();save(p,q)

if __name__=='__main__':main()
