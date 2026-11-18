"""Sequential continuation after restoring a cross-scan HP fixture failure."""
import json, os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'测试证据/内机实测_20261105/BENCH_V1052_V1239'
previous=json.loads((D/'remaining529_resume_batches.json').read_text('utf8'))
recovery=max(D.glob('remaining571_529_HP_fixture_recovery_*.json'),key=lambda p:p.stat().st_mtime)
r=json.loads(recovery.read_text('utf8'))
assert r.get('restored') and not r.get('cleanup_error'),recovery
journal={'batches':previous['batches'][:2], 'prior_failed_run':previous,
         'fixture_recovery':str(recovery.relative_to(ROOT)), 'serial_writers_overlap':False}
destination=D/'remaining529_HP_resumed_batches.json'
destination.write_text(json.dumps(journal,ensure_ascii=False,indent=2),'utf8')
env=dict(os.environ,PSC_BENCH_PREVIOUS_BATCH_JOURNAL=destination.name,PSC_HP_ONLY_SECOND='1')
for script in ('remaining529_defrost_highpressure_board_20261105.py','remaining529_cycles_soak_board_20261105.py'):
    log=ROOT/'.codex-tmp'/(Path(script).stem+'_r4.log')
    print('START',script,flush=True)
    with log.open('w',encoding='utf8') as f:
        run=subprocess.run([sys.executable,'-u',str(ROOT/'tools'/script)],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
    journal['batches'].append({'script':script,'exit_code':run.returncode,'log':str(log.relative_to(ROOT))})
    destination.write_text(json.dumps(journal,ensure_ascii=False,indent=2),'utf8')
    print('END',script,run.returncode,flush=True)
    if run.returncode:break
