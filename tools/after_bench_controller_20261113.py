"""Continue formal tests after the already-running BENCH controller exits."""
from pathlib import Path
import ctypes
import json
import subprocess
import sys
import time

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/逐项测试_20261113'
def save(p,q):
    t=p.with_suffix('.tmp');t.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');t.replace(p)
def alive(pid):
    k=ctypes.windll.kernel32;k.OpenProcess.restype=ctypes.c_void_p
    h=k.OpenProcess(0x100000,False,pid)
    if not h:return False
    try:return k.WaitForSingleObject(ctypes.c_void_p(h),0)==0x102
    finally:k.CloseHandle(ctypes.c_void_p(h))
def main():
    p=D/'formal_followup_controller.json';assert not p.exists()
    q=dict(status='waiting_for_bench_controller',started=time.strftime('%Y-%m-%dT%H:%M:%S%z'),steps=[])
    save(p,q)
    while True:
        prior=json.loads((D/'controller.json').read_text('utf8'))
        if not alive(prior['pid']):break
        time.sleep(5)
    assert prior['status']=='bench_executed_review_results_then_continue_formal',prior['status']
    assert len(prior['executed'])==len(prior['tasks'])
    if (R/'.codex-tmp/continuous_v1055_pause.request').exists():
        q['status']='paused_by_user';save(p,q);return
    def call(key,script,args):
        entry=dict(key=key,started=time.strftime('%Y-%m-%dT%H:%M:%S%z'));q['steps'].append(entry)
        with (D/(key+'.log')).open('w',encoding='utf8') as out:
            child=subprocess.Popen([sys.executable,'-X','utf8','-u',script,*args],cwd=R,stdout=out,stderr=subprocess.STDOUT)
            entry['pid']=child.pid;q['active']=entry;save(p,q);rc=child.wait()
        entry.update(exitcode=rc,finished=time.strftime('%Y-%m-%dT%H:%M:%S%z'));q.pop('active',None);save(p,q);return rc
    q['status']='formal_queue_running';save(p,q)
    call('formal_queue','tools/production_queue_controller_20261113.py',[])
    assert (D/'production_activated.json').exists(),'No verified current-version PRODUCTION deployment'
    assert call('pre_stability_audit','tools/production_queue_dispatch_20261113.py',['audit'])==0
    if (R/'.codex-tmp/continuous_v1055_pause.request').exists():
        q['status']='paused_by_user';save(p,q);return
    q['status']='two_hour_stability_running';save(p,q)
    call('two_hour_stability','tools/production_queue_dispatch_20261113.py',['soak'])
    assert call('final_formal_audit','tools/production_queue_dispatch_20261113.py',['final-audit'])==0
    q['status']='scheduled_batches_executed_review_per_case_results';save(p,q)
if __name__=='__main__':main()
