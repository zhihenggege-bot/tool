"""One serial writer; finish, restore and audit each batch before continuing."""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
DAY=ROOT/'测试证据/台架执行_20261111'
TASKS=DAY/'pending_continuation_tasks.json'
PAUSE=ROOT/'.codex-tmp/continuous_v1055_pause.request'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--after-process',type=int)
    parser.add_argument('--resume-journal')
    args=parser.parse_args()
    path=DAY/('pending_controller_'+time.strftime('%H%M%S')+'.json')
    log=dict(started=time.strftime('%Y-%m-%dT%H:%M:%S%z'),steps=[],status='running',firmware_changed=False)
    if args.resume_journal:
        previous=(ROOT/args.resume_journal).resolve();assert previous.is_relative_to(DAY.resolve())
        prior=json.loads(previous.read_text('utf8'))
        assert prior.get('status')=='restoration_or_controller_error','Only resume a stopped controller'
        log.update(resumed_from=previous.relative_to(ROOT).as_posix(),completed_tasks=prior.get('completed_tasks',[]))
    def save():path.write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf8')
    def call(arguments,kind):
        entry=dict(kind=kind,arguments=arguments,started=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
        log['steps'].append(entry);save()
        print('QUEUE START',kind,*arguments,flush=True)
        result=subprocess.run([sys.executable,'-X','utf8','-u',*arguments],cwd=ROOT)
        entry.update(exitcode=result.returncode,finished=time.strftime('%Y-%m-%dT%H:%M:%S%z'));save()
        print('QUEUE END',kind,result.returncode,flush=True)
        return result.returncode
    def audit():
        for _ in range(3):
            if call(['tools/audit_shared_type_board_20261110.py'],'independent restoration audit')==0:return
            time.sleep(2)
        raise RuntimeError('Restoration could not be verified; hardware queue stopped with evidence retained')
    try:
        if args.after_process:
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.OpenProcess.restype=ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            handle=kernel.OpenProcess(0x00100000,False,args.after_process)
            if handle:
                try:
                    print('QUEUE waiting for active predecessor',args.after_process,flush=True)
                    while kernel.WaitForSingleObject(handle,1000)==258:pass
                finally:kernel.CloseHandle(handle)
        audit()
        call(['tools/record_bench_queue_20261111.py'],'publish predecessor evidence')
        completed=set(log.get('completed_tasks',[]))
        while True:
            if PAUSE.exists():
                log['status']='paused_by_user';break
            tasks=json.loads(TASKS.read_text('utf8'))
            remaining=[t for t in tasks if t['key'] not in completed]
            if not remaining:break
            task=remaining[0]
            call(task['args'],task['key'])
            audit()
            call(['tools/record_bench_queue_20261111.py'],'publish measured scope')
            completed.add(task['key']);log['completed_tasks']=sorted(completed);save()
        if log['status']=='running':
            call(['tools/finalize_bench_20261111.py'],'reconcile remaining rows')
            log['status']='scheduled_batches_finished_see_remaining_queue'
    except BaseException as exc:
        log.update(status='restoration_or_controller_error',error=repr(exc));save();raise
    finally:
        log['finished']=time.strftime('%Y-%m-%dT%H:%M:%S%z');save()
        print('QUEUE EVIDENCE',path,flush=True)


if __name__=='__main__':main()
