"""Wait without hardware access, then independently verify and audit recovery."""
import argparse,json,os,subprocess,sys,time
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'测试证据/内机实测_20261105/BENCH_V1055_V1239'

def now():return datetime.now().astimezone().isoformat(timespec='seconds')

def main():
    p=argparse.ArgumentParser();p.add_argument('--after',type=Path,required=True);a=p.parse_args()
    dependency=a.after.resolve();began=time.monotonic()
    journal=BASE/('continuous_finalization_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
    log=dict(started=now(),dependency=dependency.relative_to(ROOT).as_posix(),read_only_until_predecessor_finished=True,actions=[])
    def save():journal.write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf8')
    save()
    while True:
        if (ROOT/'.codex-tmp/continuous_v1055_pause.request').exists():
            log.update(status='pause_requested_no_hardware_access',finished=now());save();return
        try:q=json.loads(dependency.read_text('utf8'))
        except (OSError,ValueError):q={}
        if q.get('finished'):break
        if time.monotonic()-began>36000:
            log.update(status='dependency_not_finished_within_10h',finished=now());save();return
        time.sleep(10)
    log['predecessor_finished']=now();save()
    for script in ('tools/check_v1055_final_readback_20261109.py','tools/audit_pending_live_20261109.py'):
        row=dict(script=script,started=now());log['actions'].append(row);save()
        proc=subprocess.run([sys.executable,'-u',script],cwd=ROOT,env={**os.environ,'PYTHONIOENCODING':'utf-8'},capture_output=True,text=True,encoding='utf8',timeout=300)
        row.update(returncode=proc.returncode,stdout=proc.stdout,stderr=proc.stderr,finished=now());save()
        if proc.returncode:print('FINALIZATION CHECK ERROR',script,proc.stdout,proc.stderr,flush=True)
    checks=sorted(BASE.glob('independent_final_readback_20261109_*.json'),key=lambda v:v.stat().st_mtime)
    final=json.loads(checks[-1].read_text('utf8')) if checks else {}
    log.update(finished=now(),independent_readback=checks[-1].relative_to(ROOT).as_posix() if checks else None,
               independent_readback_passed=final.get('passed') is True)
    save()
    with (ROOT/'持续测试进度_内机V10.55_20261109.md').open('a',encoding='utf8') as f:
        f.write('\n连续队列结束后独立回读：'+('通过' if log['independent_readback_passed'] else '有异常，见证据，未自动判通过')+'。\n\n[队列终检日志]('+journal.relative_to(ROOT).as_posix()+')\n')
    print('CONTINUOUS FINALIZATION',log['independent_readback_passed'],journal,flush=True)

if __name__=='__main__':main()
