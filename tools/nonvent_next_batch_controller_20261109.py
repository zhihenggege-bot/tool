"""Single serial writer, continue only after predecessor restores completely."""
from v1055_bench_context_20261109 import *
from nonvent_supplement_v1055_20261109 import restored_latest
from continuous_special_stages_v1055_20261109 import paused
import subprocess,sys,os


def main():
    p=argparse.ArgumentParser();p.add_argument('--wait-pid',type=int);a=p.parse_args()
    journal=D/('nonvent_next_batch_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=now(),status='waiting_without_hardware',actions=[],ventilation='Deferred by user');dump(journal,q)
    if a.wait_pid:
        while True:
            paused()
            x=subprocess.run(['pwsh','-NoProfile','-Command',f'if (Get-Process -Id {a.wait_pid} -ErrorAction SilentlyContinue) {{ exit 1 }} else {{ exit 0 }}'],capture_output=True)
            if x.returncode==0:break
            time.sleep(3)
    q['status']='running';dump(journal,q)
    def invoke(args):
        row=dict(args=args,started=now(),status='running');q['actions'].append(row);dump(journal,q)
        log=D/('next_batch_'+time.strftime('%H%M%S')+'_'+Path(args[0]).stem+'.log')
        env=dict(os.environ,PYTHONIOENCODING='utf-8')
        with log.open('w',encoding='utf8') as f:
            r=subprocess.run([sys.executable,'-u',*args],cwd=R,stdout=f,stderr=subprocess.STDOUT,env=env)
        row.update(finished=now(),returncode=r.returncode,status='finished_see_per_case_scope' if r.returncode==0 else 'failed_or_unavailable',log=log.relative_to(R).as_posix());dump(journal,q)
        print('NEXT BATCH',row['status'],args,flush=True)
        return r.returncode
    try:
        restored_latest()
        assert invoke(['tools/check_v1055_final_readback_20261109.py'])==0
        for args in (
            ['tools/nonvent_eev_pair_live_20261109.py','1'],
            ['tools/nonvent_ntc_input_boundaries_20261109.py'],
            ['tools/nonvent_ntc_input_boundaries_20261109.py','--exact'],
            ['tools/nonvent_da8_isolation_live_20261109.py'],
        ):
            paused();restored_latest();invoke(args);restored_latest()
            assert invoke(['tools/check_v1055_final_readback_20261109.py'])==0
            for script in ('tools/audit_pending_live_20261109.py','tools/report_current_gaps_v1055_20261109.py'):
                assert invoke([script])==0
        q['status']='completed'
    except BaseException:q['error']=traceback.format_exc();q['status']='stopped_on_error';raise
    finally:q['finished']=now();dump(journal,q)
    print('NEXT NONVENT BATCH COMPLETE',journal,flush=True)


if __name__=='__main__':main()
