"""Continue only the authorized four follow-ups after old batches restore.

Single controller, one hardware writer. No full-queue or soak restart.
Failures remain in journals; restored live batches continue to next scope.
"""
import json
from pathlib import Path
import subprocess
import sys
import time
import argparse

R=Path(__file__).resolve().parents[1]
D=R/'测试证据/四项复核_20261112/restart_fix'
OLD=R/'测试证据/四项复核_20261112/four_controller_105025.json'
PAUSE=R/'.codex-tmp/four_followups_pause.request'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume-after-deploy',action='store_true')
    args=parser.parse_args()
    D.mkdir(exist_ok=True)
    path=D/('fix_controller_'+time.strftime('%H%M%S')+'.json')
    q=dict(started=time.strftime('%Y-%m-%dT%H:%M:%S%z'),status='waiting_prior_restoration',steps=[],
        scope='Only four follow-ups. Full queue, limited/formal items and two-hour soak remain separate.')
    def save():
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
    def call(key,script,args=(),required=True):
        if PAUSE.exists():raise InterruptedError('User pause requested')
        s=dict(key=key,started=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
        log=D/(path.stem+'_'+key+'.log');s['log']=str(log.relative_to(R));q['steps'].append(s);save()
        with log.open('w',encoding='utf8') as out:
            p=subprocess.Popen([sys.executable,'-X','utf8','-u','tools/'+script,*args],cwd=R,stdout=out,stderr=subprocess.STDOUT)
            s['pid']=p.pid;save();s['exitcode']=p.wait()
        s['finished']=time.strftime('%Y-%m-%dT%H:%M:%S%z');save()
        if required and s['exitcode']:raise RuntimeError('Required step failed: '+key)
    try:
        save()
        while True:
            prior=json.loads(OLD.read_text('utf8'))
            if prior['status']!='running':break
            if PAUSE.exists():raise InterruptedError('User pause requested')
            time.sleep(5)
        assert prior['status']=='finished_review_case_results',prior
        assert set(prior['completed'])=={'fixed50Hz_span','fan_and_contact_protection','fixed_two_speed_cooling','restart_60','restart_120'}
        assert prior['steps'][-1]['key'].startswith('after_restart_120_audit') and prior['steps'][-1]['exitcode']==0
        q['status']='running';save()
        if args.resume_after_deploy:
            previous=json.loads((D/'fix_controller_114801.json').read_text('utf8'))
            done={s['key'] for s in previous['steps'] if s.get('exitcode')==0}
            assert {'build','restart_guard_ARM','typeII_recovery_ARM','adc_fixture_ARM','focused_ARM','shared_ARM','protection_ARM','lifecycle_ARM','comm_ARM','fan_threshold_ARM','scaling_ARM'}<=done
            flash=json.loads((D/'flash.json').read_text('utf8'))
            assert len(flash['boards'])==3 and all(b['flash_verified'] for b in flash['boards'])
            q['resume_source']='fix_controller_114801.json';save()
            call('resume_full_image_and_restoration_audit','bench_restart_fix_20261112.py',['audit'])
        else:
            call('prebuild_restoration_audit','bench_four_followups_20261112.py',['audit'])
            call('build','build_restart_guard_v1060_20261112.py')
            call('restart_guard_ARM','test_restart_guard_arm_20261112.py')
            call('typeII_recovery_ARM','test_typeII_recovery_arm_20261112.py')
            call('adc_fixture_ARM','test_adc_fixture_scale_20261112.py')
            for suite in ('focused','shared','protection','lifecycle','comm','fan_threshold','scaling'):
                call(suite+'_ARM','regress_restart_guard_preservation_20261112.py',[suite])
            call('deploy','bench_restart_fix_20261112.py',['deploy'])
        for key,script,args in (
            ('typeII_recovery_live','bench_typeII_recovery_fix_20261112.py',()),
            ('restart60_live','bench_restart_fix_20261112.py',('minrun','--value','60')),
            ('restart120_live','bench_restart_fix_20261112.py',('minrun','--value','120')),
            ('stable_LP_live','bench_restart_fix_20261112.py',('stable-lp',))):
            call(key,script,args,required=False)
            # Even a failed stimulus must restore before the next one starts.
            call('restore_audit_after_'+key,'bench_restart_fix_20261112.py',['audit'])
        call('typeII_OR_robust_live','bench_typeII_OR_robust_20261112.py',required=False)
        call('restore_audit_after_OR_robust','bench_restart_fix_20261112.py',['audit'])
        q['status']='finished_review_case_results'
    except BaseException as exc:
        q.update(status='needs_attention',error=repr(exc));raise
    finally:
        q['updated']=time.strftime('%Y-%m-%dT%H:%M:%S%z');save()


if __name__=='__main__':main()
