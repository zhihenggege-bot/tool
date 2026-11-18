"""Resume after a bounded poll-convergence retest; keep the failed run intact."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'测试证据/内机实测_20261105/BENCH_V1052_V1239'

def main():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=(ctypes.c_void_p,ctypes.c_uint32)
    kernel.CloseHandle.argtypes=(ctypes.c_void_p,)
    handle=kernel.OpenProcess(0x100000,False,int(sys.argv[1]))
    if handle:
        while kernel.WaitForSingleObject(handle,1000)==258:pass
        kernel.CloseHandle(handle)
    p=max(D.glob('remaining571_529_allocation_defrost_*.json'),key=lambda p:p.stat().st_mtime)
    allocation=json.loads(p.read_text('utf8'))
    assert allocation.get('passed') and allocation.get('restored') and not allocation.get('cleanup_error'),p
    old=json.loads((D/'continuation_batches.json').read_text('utf8'))
    fan=old['batches'][0]
    assert fan['exit_code']==0
    journal={'batches':[fan,{'script':'remaining529_allocation_defrost_board_20261105.py',
        'exit_code':0,'evidence':str(p.relative_to(ROOT))}],
        'initial_failure_preserved':old,'serial_writers_overlap':False}
    destination=D/'remaining529_resume_batches.json'
    destination.write_text(json.dumps(journal,ensure_ascii=False,indent=2),'utf8')
    env=dict(os.environ,PSC_BENCH_PREVIOUS_BATCH_JOURNAL=destination.name)
    for script in ('remaining529_defrost_highpressure_board_20261105.py',
                   'remaining529_cycles_soak_board_20261105.py'):
        log=ROOT/'.codex-tmp'/(Path(script).stem+'_resumed.log')
        print('START',script,flush=True)
        with log.open('w',encoding='utf8') as f:
            r=subprocess.run([sys.executable,'-u',str(ROOT/'tools'/script)],cwd=ROOT,
                env=env,stdout=f,stderr=subprocess.STDOUT)
        journal['batches'].append({'script':script,'exit_code':r.returncode,'log':str(log.relative_to(ROOT))})
        destination.write_text(json.dumps(journal,ensure_ascii=False,indent=2),'utf8')
        print('END',script,r.returncode,flush=True)
        if r.returncode:break

if __name__=='__main__':main()
